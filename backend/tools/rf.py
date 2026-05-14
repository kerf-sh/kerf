import json
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


run_rf_study_spec = ToolSpec(
    name="run_rf_study",
    description="Run an S-parameter analysis on a .rf-study file using scikit-rf. Performs Smith chart analysis, VSWR, return loss, and insertion loss on touchstone (.sNp) data.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "port_impedance": {"type": "number", "description": "Reference impedance in ohms for renormalization (default 50)."},
            "freq_unit": {"type": "string", "enum": ["Hz", "kHz", "MHz", "GHz"], "description": "Frequency unit for output plots (default GHz)."},
        },
        "required": ["file_id"],
    },
)


@register(run_rf_study_spec, write=True)
async def run_rf_study(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    port_z = a.get("port_impedance", 50.0)
    freq_unit = a.get("freq_unit", "GHz")
    spec = {
        "file_id": file_id,
        "port_impedance": port_z,
        "freq_unit": freq_unit,
    }
    spec_json = json.dumps(spec)
    row = await ctx.pool.fetchrow(
        """INSERT INTO rf_jobs (file_id, project_id, input_spec)
           VALUES ($1, $2, $3)
           ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
           DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
               started_at = NULL, finished_at = NULL
           RETURNING id""",
        file_id, ctx.project_id, spec_json,
    )
    if not row:
        return err_payload("failed to enqueue RF job", "ERROR")
    return ok_payload({
        "job_id": str(row["id"]),
        "status": "queued",
        "message": "RF study job enqueued. Poll rf_job_status(file_id) for results.",
    })


rf_job_status_spec = ToolSpec(
    name="rf_job_status",
    description="Poll the status of an RF study analysis job. Returns job status, and when complete the S-parameter analysis results including Smith chart SVG, VSWR, return loss, and insertion loss.",
    input_schema={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)


@register(rf_job_status_spec)
async def rf_job_status(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    row = await ctx.pool.fetchrow(
        """SELECT status, result_json, error FROM rf_jobs
           WHERE file_id = $1 AND project_id = $2
           ORDER BY created_at DESC LIMIT 1""",
        file_id, ctx.project_id,
    )
    if not row:
        return err_payload("RF job not found", "NOT_FOUND")
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


import_touchstone_spec = ToolSpec(
    name="import_touchstone",
    description="Import a Touchstone (.sNp) file and create a .rf-study file. Supports S1P, S2P, S3P, S4P formats with automatic renormalization to the specified port impedance.",
    input_schema={
        "type": "object",
        "properties": {
            "touchstone_file_id": {"type": "string"},
            "name": {"type": "string"},
            "port_impedance": {"type": "number", "description": "Reference impedance in ohms (default 50)."},
        },
        "required": ["touchstone_file_id", "name"],
    },
)


@register(import_touchstone_spec, write=True)
async def import_touchstone(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    touchstone_file_id = a.get("touchstone_file_id", "")
    name = a.get("name", "")
    if not touchstone_file_id:
        return err_payload("touchstone_file_id is required", "BAD_ARGS")
    if not name:
        return err_payload("name is required", "BAD_ARGS")
    port_z = a.get("port_impedance", 50.0)
    row = await ctx.pool.fetchrow(
        """SELECT file_data, file_name FROM project_files
           WHERE id = $1 AND project_id = $2""",
        touchstone_file_id, ctx.project_id,
    )
    if not row:
        return err_payload("Touchstone file not found", "NOT_FOUND")
    touchstone_data = row["file_data"]
    touchstone_file_name = row["file_name"]
    import base64
    rf_study_doc = {
        "version": 1,
        "name": name,
        "source_file": touchstone_file_name,
        "port_impedance": port_z,
        "frequency_unit": "GHz",
        "touchstone_b64": base64.b64encode(touchstone_data).hex() if isinstance(touchstone_data, bytes) else base64.b64encode(touchstone_data.encode()).hex(),
        "results": {"status": "pending"},
    }
    rf_study_json = json.dumps(rf_study_doc)
    new_row = await ctx.pool.fetchrow(
        """INSERT INTO project_files (project_id, file_name, file_data, content_type, file_kind, created_by)
           VALUES ($1, $2, $3, 'application/json', 'rf-study', $4)
           RETURNING id""",
        ctx.project_id, name + ".rf-study", rf_study_json.encode(), ctx.user_id,
    )
    return ok_payload({
        "file_id": str(new_row["id"]),
        "file_name": name + ".rf-study",
        "status": "created",
    })
