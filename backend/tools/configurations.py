import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def as_string(v) -> str:
    if isinstance(v, str):
        return v
    return ""


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


add_configuration_spec = ToolSpec(
    name="add_configuration",
    description="Append (or update) a configuration on a file that supports per-file parameter overrides — Part (.part), Feature (.feature), or Sketch (.sketch).",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "id": {"type": "string"},
            "label": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["file_id", "id"],
    },
)


@register(add_configuration_spec, write=True)
async def run_add_configuration(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    config_id = a.get("id", "").strip()
    label = a.get("label", "")
    params = a.get("params", {})

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not config_id:
        return err_payload("id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT name, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("file not found", "NOT_FOUND")

    kind = row["kind"]
    if kind not in ("part", "feature", "sketch"):
        return err_payload(f"file kind {kind} does not support configurations", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        return err_payload("file is not valid JSON object", "BAD_FILE")

    existing = []
    if "configurations" in doc:
        raw = doc["configurations"]
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    existing.append(item)

    if not label:
        label = config_id

    updated = False
    for i, cfg in enumerate(existing):
        if as_string(cfg.get("id")) == config_id:
            existing[i] = {"id": config_id, "label": label, "params": params}
            updated = True
            break
    if not updated:
        existing.append({"id": config_id, "label": label, "params": params})

    doc["configurations"] = existing

    if "default_config" not in doc or not as_string(doc.get("default_config")):
        doc["default_config"] = config_id

    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({
        "file_id": file_id_str,
        "name": row["name"],
        "id": config_id,
        "label": label,
        "updated": updated,
    })


set_active_config_spec = ToolSpec(
    name="set_active_config",
    description="Pin a configuration on an assembly's component.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
            "component_id": {"type": "string"},
            "config_id": {"type": "string"},
        },
        "required": ["assembly_file_id", "component_id"],
    },
)


@register(set_active_config_spec, write=True)
async def run_set_active_config(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    component_id = a.get("component_id", "").strip()
    config_id = a.get("config_id", "").strip()

    if not assembly_file_id or not component_id:
        return err_payload("assembly_file_id and component_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload("file is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        return err_payload("file is not valid JSON object", "BAD_FILE")

    raw_components = doc.get("components")
    if raw_components is None:
        raw_components = doc.get("children")

    if not isinstance(raw_components, list):
        return err_payload("components is not a list", "BAD_FILE")

    found = False
    for i, entry in enumerate(raw_components):
        if not isinstance(entry, dict):
            continue
        if as_string(entry.get("id")) != component_id:
            continue
        if config_id == "":
            if "config_id" in entry:
                del entry["config_id"]
        else:
            entry["config_id"] = config_id
        raw_components[i] = entry
        found = True
        break

    if not found:
        return err_payload(f"component {component_id} not found in assembly", "NOT_FOUND")

    doc["components"] = raw_components
    if "children" in doc:
        del doc["children"]

    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "component_id": component_id,
        "config_id": config_id,
        "cleared": config_id == "",
    })