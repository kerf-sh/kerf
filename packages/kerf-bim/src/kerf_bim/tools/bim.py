import base64
import json
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx


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


async def ensure_folders(ctx: ProjectCtx, parts: list) -> uuid.UUID:
    if not parts:
        return None
    parent_id = None
    for i in range(len(parts)):
        folder_name = parts[i]
        parent_path = "/" + "/".join(parts[:i]) if i > 0 else "/"
        if parent_path == "/":
            parent_id = None
        else:
            parent_row = await ctx.pool.fetchrow(
                "SELECT id FROM files WHERE project_id = $1 AND path = $2 AND kind = 'folder' AND deleted_at IS NULL",
                ctx.project_id, parent_path,
            )
            parent_id = parent_row["id"] if parent_row else None

        existing = await ctx.pool.fetchrow(
            "SELECT id, kind FROM files WHERE project_id = $1 AND name = $2 AND parent_id IS NOT DISTINCT FROM $3 AND deleted_at IS NULL",
            ctx.project_id, folder_name, parent_id,
        )
        if existing:
            if existing["kind"] != "folder":
                return None
            parent_id = existing["id"]
        else:
            new_id = await ctx.pool.fetchval(
                "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'folder', '{}') RETURNING id",
                ctx.project_id, parent_id, folder_name,
            )
            parent_id = new_id
    return parent_id


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


def serialize_bim(d: dict) -> str:
    if d.get("version", 0) == 0:
        d["version"] = 1
    return json.dumps(d, indent="  ")


create_bim_spec = ToolSpec(
    name="create_bim",
    description="Create a new empty .bim architecture file (IFC4 BIM model). After creation, populate by editing the JSON via write_file / edit_file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "name": {"type": "string"},
            "site": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "elevation": {"type": "number"},
                },
            },
        },
        "required": ["path"],
    },
)


@register(create_bim_spec, write=True)
async def run_create_bim(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")
    site = a.get("site")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    if not clean.lower().endswith(".bim"):
        return err_payload("path must end with .bim", "BAD_KIND")

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    parts = [p for p in clean.strip("/").split("/") if p]
    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    doc = {"version": 1, "name": name}
    if site:
        doc["site"] = site

    body = serialize_bim(doc)

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'bim', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id)})


read_bim_spec = ToolSpec(
    name="read_bim",
    description="Read a .bim architecture file and return its full JSON body.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
)


@register(read_bim_spec)
async def run_read_bim(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    if not path:
        return err_payload("path is required", "BAD_ARGS")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND path = $2 AND kind = 'bim'",
        ctx.project_id, clean,
    )
    if not row:
        return err_payload("file not found or not a .bim", "NOT_FOUND")

    content = row["content"] if row["content"] else ""

    return ok_payload({
        "path": clean,
        "content": content,
    })


compile_bim_to_ifc_spec = ToolSpec(
    name="compile_bim_to_ifc",
    description="Compile a .bim architecture file to an IFC4 .ifc binary using IfcOpenShell. The .ifc is stored in the same project and returned as a base64-encoded blob.",
    input_schema={
        "type": "object",
        "properties": {
            "bim_path": {"type": "string"},
        },
        "required": ["bim_path"],
    },
)


@register(compile_bim_to_ifc_spec, write=True)
async def run_compile_bim_to_ifc(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    bim_path = a.get("bim_path", "")
    if not bim_path:
        return err_payload("bim_path is required", "BAD_ARGS")

    clean = bim_path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND path = $2 AND kind = 'bim'",
        ctx.project_id, clean,
    )
    if not row:
        return err_payload("bim file not found", "NOT_FOUND")

    content = row["content"] if row["content"] else ""

    import httpx
    pyworker_url = "http://localhost:9090/compile-bim"
    payload = {"bim_content": content}

    try:
        resp = ctx.http_client.post(pyworker_url, json=payload, timeout=60.0)
    except Exception as e:
        return err_payload(f"compile worker unavailable: {e}", "WORKER_ERROR")

    if resp.status_code != 200:
        return err_payload(f"compile worker returned status {resp.status_code}", "WORKER_ERROR")

    try:
        result = resp.json()
    except Exception:
        return err_payload("invalid compile response", "ERROR")

    ifc_base64 = result.get("ifc_base64", "")
    ifc_path = result.get("ifc_path", "")

    if not ifc_base64:
        return err_payload("no ifc_base64 in response", "ERROR")

    try:
        ifc_bytes = base64.b64decode(ifc_base64)
    except Exception:
        return err_payload("invalid ifc response", "ERROR")

    parts = [p for p in clean.strip("/").split("/") if p]
    leaf = parts[-1] if parts else "output.ifc"
    if not ifc_path:
        ifc_path = leaf.rsplit(".bim", 1)[0] + ".ifc" if leaf.endswith(".bim") else leaf + ".ifc"

    parent_id = await ensure_folders(ctx, parts[:-1]) if len(parts) > 1 else None

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'ifc', $4) RETURNING id",
        ctx.project_id, parent_id, ifc_path, ifc_bytes,
    )

    return ok_payload({
        "ifc_path": ifc_path,
        "ifc_id": str(new_id),
    })


read_ifc_spec = ToolSpec(
    name="read_ifc",
    description="Read the raw binary content of an existing .ifc file from the project, returned as base64.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
)


@register(read_ifc_spec)
async def run_read_ifc(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    if not path:
        return err_payload("path is required", "BAD_ARGS")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND path = $2 AND kind = 'ifc'",
        ctx.project_id, clean,
    )
    if not row:
        return err_payload("ifc file not found", "NOT_FOUND")

    content = row["content"]
    if isinstance(content, str):
        content_bytes = content.encode()
    else:
        content_bytes = content

    encoded = base64.b64encode(content_bytes).decode()

    return ok_payload({
        "path": clean,
        "ifc_base64": encoded,
    })