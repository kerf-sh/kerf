import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


async def resolve_path(ctx: ProjectCtx, path: str) -> dict:
    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return {"exists": False}
    row = await ctx.pool.fetchrow(
        "SELECT id, parent_id, name, kind FROM files WHERE project_id = $1 AND path = $2 AND deleted_at IS NULL",
        ctx.project_id, clean,
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "id": row["id"],
        "parent_id": row["parent_id"],
        "name": row["name"],
        "kind": row["kind"],
    }


async def record_revision_for_file(ctx: ProjectCtx, file_id: uuid.UUID, content: str, source: str):
    cap = ctx.file_revisions_max if ctx.file_revisions_max > 0 else 200
    new_id = uuid.uuid4()
    preview = content[:200] if len(content) > 200 else content
    latest = await ctx.pool.fetchrow(
        "SELECT id, kind FROM file_revisions WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
        file_id,
    )
    user_id = ctx.user_id if ctx.user_id != uuid.Nil else None
    if latest is None or latest["kind"] == "base":
        diffs_after = 0
    else:
        diffs_after = await ctx.pool.fetchval(
            "SELECT COUNT(*) FROM file_revisions WHERE file_id = $1 AND kind = 'diff' AND created_at > COALESCE((SELECT MAX(created_at) FROM file_revisions WHERE file_id = $1 AND kind = 'base'), 'epoch'::timestamptz)",
            file_id,
        )
    make_base = latest is None or diffs_after >= 20
    import gzip
    import base64
    if make_base:
        gz = gzip.compress(content.encode())
        await ctx.pool.execute(
            "INSERT INTO file_revisions(id, file_id, content, content_gz, kind, source, user_id, content_preview) VALUES ($1, $2, $3, $4, 'base', $5, $6, $7)",
            new_id, file_id, content, base64.b64encode(gz).decode(), source, user_id, preview,
        )
    else:
        parent_content_row = await ctx.pool.fetchrow(
            "SELECT content_gz FROM file_revisions WHERE id = $1",
            latest["id"],
        )
        parent_content = content
        if parent_content_row and parent_content_row["content_gz"]:
            parent_content = gzip.decompress(parent_content_row["content_gz"]).decode()
        delta = content
        gz = gzip.compress(delta.encode())
        await ctx.pool.execute(
            "INSERT INTO file_revisions(id, file_id, content, content_gz, kind, parent_revision_id, source, user_id, content_preview) VALUES ($1, $2, '', $3, 'diff', $4, $5, $6, $7)",
            new_id, file_id, base64.b64encode(gz).decode(), latest["id"], source, user_id, preview,
        )
    await ctx.pool.execute(
        "DELETE FROM file_revisions WHERE file_id = $1 AND created_at < (SELECT created_at FROM file_revisions WHERE file_id = $1 ORDER BY created_at DESC OFFSET $2 LIMIT 1)",
        file_id, cap,
    )
    return new_id


def parse_topo_content(s: str) -> dict:
    if not s or not s.strip():
        return {"version": 1, "results": {"warnings": [], "errors": []}}
    try:
        d = json.loads(s)
    except Exception:
        return {"version": 1, "results": {"warnings": [], "errors": []}}
    if d.get("version", 0) == 0:
        d["version"] = 1
    if "max_iterations" not in d or d["max_iterations"] == 0:
        d["max_iterations"] = 200
    if "penalization_power" not in d or d["penalization_power"] == 0:
        d["penalization_power"] = 3
    if "filter_radius_mm" not in d or d["filter_radius_mm"] == 0:
        d["filter_radius_mm"] = 1.5
    if "convergence_tolerance" not in d or d["convergence_tolerance"] == 0:
        d["convergence_tolerance"] = 1e-4
    if "volume_fraction" not in d or d["volume_fraction"] == 0:
        d["volume_fraction"] = 0.3
    if "results" not in d:
        d["results"] = {}
    if "warnings" not in d["results"]:
        d["results"]["warnings"] = []
    if "errors" not in d["results"]:
        d["results"]["errors"] = []
    return d


def serialize_topo_content(d: dict) -> str:
    if d.get("version", 0) == 0:
        d["version"] = 1
    if "warnings" not in d.get("results", {}):
        d["results"]["warnings"] = []
    if "errors" not in d.get("results", {}):
        d["results"]["errors"] = []
    return json.dumps(d, indent="  ")


topo_run_spec = ToolSpec(
    name="topo_run",
    description="Submit a topology-optimization (SIMP via FEniCSx) job for a .topo file.",
    input_schema={
        "type": "object",
        "properties": {"topo_path": {"type": "string"}},
        "required": ["topo_path"],
    },
)


@register(topo_run_spec, write=True)
async def run_topo_run(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    topo_path = a.get("topo_path", "").strip()
    if not topo_path:
        return err_payload("topo_path is required", "BAD_ARGS")

    rp = await resolve_path(ctx, topo_path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {topo_path}", "NOT_FOUND")

    if rp.get("kind") != "topo":
        return err_payload(f"path is not a .topo file (kind={rp.get('kind')})", "BAD_KIND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    content = row["content"] if row and row["content"] else ""

    doc = parse_topo_content(content)

    ds_fp = doc.get("design_space_feature_path", "").strip()
    mat_fp = doc.get("material_path", "").strip()
    vol_frac = doc.get("volume_fraction", 0)
    max_iter = doc.get("max_iterations", 200)
    penal_pow = doc.get("penalization_power", 3)
    filter_rad = doc.get("filter_radius_mm", 1.5)
    conv_tol = doc.get("convergence_tolerance", 1e-4)

    if not ds_fp:
        return err_payload("topo file is missing design_space_feature_path", "BAD_TOPO")
    if not mat_fp:
        return err_payload("topo file is missing material_path", "BAD_TOPO")
    if vol_frac <= 0 or vol_frac >= 1:
        return err_payload("volume_fraction must be in (0, 1)", "BAD_TOPO")
    if max_iter <= 0:
        return err_payload("max_iterations must be > 0", "BAD_TOPO")

    ds_rp = await resolve_path(ctx, ds_fp)
    if not ds_rp.get("exists"):
        return err_payload(f"design_space_feature_path not found: {ds_fp}", "NOT_FOUND")
    if ds_rp.get("kind") != "feature":
        return err_payload("design_space_feature_path is not a .feature file", "BAD_TOPO")

    mat_rp = await resolve_path(ctx, mat_fp)
    if not mat_rp.get("exists"):
        return err_payload(f"material_path not found: {mat_fp}", "NOT_FOUND")
    if mat_rp.get("kind") != "material":
        return err_payload("material_path is not a .material file", "BAD_TOPO")

    payload = {
        "project_id": str(ctx.project_id),
        "topo_file_id": str(rp["id"]),
        "feature_file_id": str(ds_rp["id"]),
        "material_file_id": str(mat_rp["id"]),
        "volume_fraction": vol_frac,
        "penalization_power": penal_pow,
        "filter_radius_mm": filter_rad,
        "max_iterations": max_iter,
        "convergence_tolerance": conv_tol,
    }

    body = json.dumps(payload)

    import httpx
    req_url = "http://localhost:9090/run-topo"
    try:
        response = ctx.http_client.post(req_url, content=body, headers={"content-type": "application/json"}, timeout=30.0)
    except Exception as e:
        doc["results"]["status"] = "pending"
        doc["results"]["warnings"] = doc["results"].get("warnings", [])
        doc["results"]["warnings"].append("Engine pending — FEniCSx not yet deployed.")
        out_body = serialize_topo_content(doc)
        await ctx.pool.execute(
            "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
            out_body, rp["id"], ctx.project_id,
        )
        await record_revision_for_file(ctx, rp["id"], out_body, "tool")
        return ok_payload({
            "status": "pending",
            "topo_path": topo_path,
            "warning": "Engine pending — FEniCSx not yet deployed.",
            "output_mesh_file_id": "",
        })

    if response.status_code != 200:
        return err_payload(f"engine returned status {response.status_code}", "WORKER_ERROR")

    try:
        engine_resp = response.json()
    except Exception:
        return err_payload("invalid engine response", "ERROR")

    status = engine_resp.get("status", "pending")
    if status == "":
        status = "pending"

    warnings = engine_resp.get("warnings") or []
    error_msg = engine_resp.get("error") or ""

    doc["results"]["status"] = status
    doc["results"]["iterations"] = engine_resp.get("iterations", 0)
    doc["results"]["output_mesh_file_id"] = engine_resp.get("output_mesh_file_id", "")

    fc = engine_resp.get("final_compliance")
    if fc:
        doc["results"]["final_compliance"] = fc

    fvf = engine_resp.get("final_volume_fraction")
    if fvf:
        doc["results"]["final_volume_fraction"] = fvf

    for w in warnings:
        if w:
            doc["results"]["warnings"].append(w)

    if error_msg:
        doc["results"]["errors"].append(error_msg)

    out_body = serialize_topo_content(doc)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        out_body, rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, rp["id"], out_body, "tool")

    return ok_payload({
        "status": status,
        "topo_path": topo_path,
        "output_mesh_file_id": engine_resp.get("output_mesh_file_id", ""),
        "final_compliance": engine_resp.get("final_compliance", 0),
        "final_volume_fraction": engine_resp.get("final_volume_fraction", 0),
        "iterations": engine_resp.get("iterations", 0),
        "errors": doc["results"].get("errors", []),
    })