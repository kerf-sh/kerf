import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


run_simulation_spec = ToolSpec(
    name="run_simulation",
    description="Run a SPICE simulation on a circuit file.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_file_id": {"type": "string"},
            "analysis": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["tran", "dc", "ac", "op"]},
                    "tstep": {"type": "string"},
                    "tstop": {"type": "string"},
                    "vstart": {"type": "number"},
                    "vstop": {"type": "number"},
                    "vstep": {"type": "number"},
                    "fstart": {"type": "number"},
                    "fstop": {"type": "number"},
                    "points": {"type": "number"},
                },
                "required": ["type"],
            },
        },
        "required": ["circuit_file_id", "analysis"],
    },
)


@register(run_simulation_spec, write=True)
async def run_simulation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_file_id = a.get("circuit_file_id", "")
    analysis = a.get("analysis", {})

    if not circuit_file_id:
        return err_payload("circuit_file_id is required", "BAD_ARGS")
    if not analysis.get("type"):
        return err_payload("analysis.type is required", "BAD_ARGS")

    spec_json = json.dumps(analysis)

    row = await ctx.pool.fetchrow(
        """INSERT INTO sim_jobs (file_id, project_id, input_spec)
           VALUES ($1, $2, $3)
           ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
           DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
               started_at = NULL, finished_at = NULL
           RETURNING id""",
        circuit_file_id, ctx.project_id, spec_json,
    )

    if not row:
        return err_payload("failed to enqueue sim job", "ERROR")

    return ok_payload({
        "job_id": str(row["id"]),
        "status": "queued",
        "message": "Simulation job enqueued. Poll sim_job_status(file_id) for results.",
        "circuit_file_id": circuit_file_id,
    })


sim_job_status_spec = ToolSpec(
    name="sim_job_status",
    description="Poll the status of a SPICE simulation job. Returns job status, and when complete the waveform results.",
    input_schema={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)


@register(sim_job_status_spec)
async def run_sim_job_status(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        """SELECT status, result_json, error FROM sim_jobs
           WHERE file_id = $1 AND project_id = $2
           ORDER BY created_at DESC LIMIT 1""",
        file_id, ctx.project_id,
    )

    if not row:
        return err_payload("sim job not found", "NOT_FOUND")

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
