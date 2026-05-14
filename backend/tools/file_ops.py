import json
import re
import uuid
from typing import Any, Optional
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def normalize_path(path: str) -> tuple[str, Optional[str]]:
    if not path.startswith("/"):
        return "", "path must be absolute"
    return path.rstrip("/"), None


def split_path(path: str) -> list[str]:
    parts = path.strip("/").split("/")
    return [p for p in parts if p]


async def resolve_path(ctx: ProjectCtx, path: str) -> dict[str, Any]:
    clean, err = normalize_path(path)
    if err:
        return {"exists": False, "error": err}

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


async def ensure_folders(ctx: ProjectCtx, parts: list[str]) -> Optional[uuid.UUID]:
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


async def path_from_file_id(ctx: ProjectCtx, file_id: uuid.UUID) -> str:
    row = await ctx.pool.fetchrow(
        "SELECT parent_id, name FROM files WHERE id = $1",
        file_id,
    )
    if not row:
        return ""
    parts = [row["name"]]
    parent_id = row["parent_id"]
    for _ in range(64):
        if parent_id is None:
            break
        prow = await ctx.pool.fetchrow(
            "SELECT parent_id, name FROM files WHERE id = $1",
            parent_id,
        )
        if not prow:
            break
        parts.insert(0, prow["name"])
        parent_id = prow["parent_id"]
    return "/" + "/".join(parts)


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

    if make_base:
        import gzip
        import base64
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
        import gzip
        import base64
        parent_content = content
        if parent_content_row and parent_content_row["content_gz"]:
            parent_content = gzip.decompress(base64.b64encode(parent_content_row["content_gz"].encode())).decode() if isinstance(parent_content_row["content_gz"], str) else gzip.decompress(parent_content_row["content_gz"])

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


list_files_spec = ToolSpec(
    name="list_files",
    description="List every file in the current project as a flat array of absolute paths.",
    input_schema={"type": "object", "properties": {}},
)


@register(list_files_spec)
async def run_list_files(ctx: ProjectCtx, args: bytes) -> str:
    rows = await ctx.pool.fetch(
        "SELECT id, parent_id, name, kind, length(content), size "
        "FROM files WHERE project_id = $1 AND deleted_at IS NULL",
        ctx.project_id,
    )

    idx: dict[uuid.UUID, dict] = {}
    all_rows = []
    for row in rows:
        r = {
            "id": row["id"],
            "parent": row["parent_id"],
            "name": row["name"],
            "kind": row["kind"],
            "clen": row["length"],
            "size": row["size"],
        }
        all_rows.append(r)
        idx[r["id"]] = r

    def path_of(uid: uuid.UUID) -> str:
        parts = []
        cur = uid
        for _ in range(64):
            if cur not in idx:
                return ""
            r = idx[cur]
            parts.insert(0, r["name"])
            if r["parent"] is None:
                break
            cur = r["parent"]
        return "/" + "/".join(parts)

    out = []
    for r in all_rows:
        size = r["size"]
        if size is None and r["kind"] != "folder" and r["kind"] != "step":
            size = r["clen"]
        out.append({"path": path_of(r["id"]), "kind": r["kind"], "size": size})

    return ok_payload({"files": out})


read_file_spec = ToolSpec(
    name="read_file",
    description="Read the full text content of a file by absolute path. Errors on binary kinds (e.g. step). Paths under '/docs/llm/' route to the embedded Kerf authoring corpus instead of the project tree (use search_kerf_docs to discover them).",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


@register(read_file_spec)
async def run_read_file(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    if not path:
        return err_payload("path is required", "BAD_ARGS")

    from . import docs
    if path.startswith("/docs/llm/"):
        body = docs.doc_corpus_read_file(path)
        if body:
            return ok_payload({"path": path, "content": body})
        return err_payload(f"doc not found: {path} (use search_kerf_docs to discover available pages)", "NOT_FOUND")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind")
    if kind == "step":
        return err_payload("cannot read binary kind 'step' as text; use the download URL", "BINARY")
    if kind == "step-ref":
        row = await ctx.pool.fetchrow(
            'SELECT content FROM files WHERE id = $1 AND project_id = $2',
            rp['id'], ctx.project_id,
        )
        if not row:
            return err_payload(f'file not found: {path}', 'NOT_FOUND')
        return ok_payload({'path': path, 'content': row['content'], 'note': 'step-ref pointer — content is JSON metadata; actual binary is in blob storage'})
    if kind == "folder":
        return err_payload("path is a folder", "IS_FOLDER")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    return ok_payload({"path": path, "content": row["content"]})


write_file_spec = ToolSpec(
    name="write_file",
    description="Replace the entire content of a text file. Creates intermediate folders if missing. Use edit_file for targeted edits.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)


@register(write_file_spec, write=True)
async def run_write_file(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    content = a.get("content", "")

    clean, err = normalize_path(path)
    if err:
        return err_payload(err, "BAD_ARGS")

    parts = split_path(clean)
    if not parts:
        return err_payload("cannot write the root", "BAD_ARGS")

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        kind = rp.get("kind")
        if kind in ("step", "folder"):
            return err_payload(f"cannot write to kind={kind}", "BAD_KIND")

        await ctx.pool.execute(
            "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
            content, rp["id"], ctx.project_id,
        )
        await record_revision_for_file(ctx, rp["id"], content, "tool")
        return ok_payload({"path": clean, "bytes": len(content)})

    low_clean = clean.lower()
    if low_clean.endswith(".sketch"):
        return err_payload("create sketches with create_sketch, not write_file", "READONLY_SKETCH")
    if low_clean.endswith(".feature"):
        return err_payload("create feature files with create_feature, not write_file", "READONLY_FEATURE")
    if low_clean.endswith(".part"):
        return err_payload("create part files with create_part, not write_file", "READONLY_PART")

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]
    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'file', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, content,
    )
    if content:
        await record_revision_for_file(ctx, new_id, content, "tool")
    return ok_payload({"path": clean, "bytes": len(content), "id": str(new_id)})


edit_file_spec = ToolSpec(
    name="edit_file",
    description="Replace a unique substring inside a text file. Errors if old_string occurs zero or more than one time. Use this for surgical edits.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
        },
        "required": ["path", "old_string", "new_string"],
    },
)


@register(edit_file_spec, write=True)
async def run_edit_file(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    old_string = a.get("old_string", "")
    new_string = a.get("new_string", "")

    if not old_string:
        return err_payload("old_string must be non-empty", "BAD_ARGS")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind")
    if kind in ("step", "folder"):
        return err_payload(f"cannot edit kind={kind}", "BAD_KIND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    content = row["content"]
    count = content.count(old_string)
    if count == 0:
        return err_payload("old_string not found", "NOT_FOUND")
    if count > 1:
        return err_payload(f"old_string is ambiguous (matched {count} times)", "AMBIGUOUS")

    updated = content.replace(old_string, new_string, 1)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        updated, rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, rp["id"], updated, "tool")
    return ok_payload({"path": path, "replaced": 1})


create_file_spec = ToolSpec(
    name="create_file",
    description="Create a new file, folder, assembly, or drawing. Auto-creates intermediate folders. kind defaults to 'file'.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "kind": {"type": "string", "enum": ["file", "folder", "assembly", "drawing"]},
        },
        "required": ["path"],
    },
)


@register(create_file_spec, write=True)
async def run_create_file(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    content = a.get("content", "")
    kind = a.get("kind", "file")

    if not kind:
        kind = "file"

    if kind == "sketch":
        return err_payload("use create_sketch to create sketches", "READONLY_SKETCH")
    if kind == "feature":
        return err_payload("use create_feature to create feature files", "READONLY_FEATURE")
    if kind == "part":
        return err_payload("use create_part to create library parts", "READONLY_PART")
    if kind == "circuit":
        return err_payload("use create_circuit to create electronics designs", "BAD_ARGS")
    if kind not in ("file", "folder", "assembly", "drawing"):
        return err_payload("invalid kind (must be file|folder|assembly|drawing)", "BAD_ARGS")

    clean, err = normalize_path(path)
    if err:
        return err_payload(err, "BAD_ARGS")

    parts = split_path(clean)
    if not parts:
        return err_payload("cannot create the root", "BAD_ARGS")

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        ctx.project_id, parent_id, leaf, kind, content,
    )

    if content:
        await record_revision_for_file(ctx, new_id, content, "tool")

    return ok_payload({"path": clean, "id": str(new_id)})


delete_file_spec = ToolSpec(
    name="delete_file",
    description="Delete the file or folder at the given absolute path (recursive for folders).",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


@register(delete_file_spec, write=True)
async def run_delete_file(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    if not path:
        return err_payload("path is required", "BAD_ARGS")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    content_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    if content_row and content_row["content"]:
        await record_revision_for_file(ctx, rp["id"], content_row["content"], "tool")

    await ctx.pool.execute(
        "UPDATE files SET deleted_at = now(), updated_at = now() WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    return ok_payload({"path": path})


search_code_spec = ToolSpec(
    name="search_code",
    description="Case-insensitive substring search across all text files in the project.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max": {"type": "integer"},
        },
        "required": ["query"],
    },
)


@register(search_code_spec)
async def run_search_code(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    query = a.get("query", "")
    if not query:
        return err_payload("query is required", "BAD_ARGS")

    max_results = a.get("max", 50)
    if max_results <= 0 or max_results > 200:
        max_results = 50

    rows = await ctx.pool.fetch(
        "SELECT id, content FROM files "
        "WHERE project_id = $1 AND kind IN ('file', 'assembly') AND deleted_at IS NULL",
        ctx.project_id,
    )

    q = query.lower()
    matches = []

    for row in rows:
        content = row["content"] or ""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if q in line.lower():
                preview = line[:200] if len(line) > 200 else line
                matches.append({"path": "", "line": i + 1, "preview": preview})
                if len(matches) >= max_results:
                    return ok_payload({"matches": matches, "truncated": True})

    return ok_payload({"matches": matches})


import_step_spec = ToolSpec(
    name="import_step",
    description="Download a STEP file from an HTTPS URL into the project. Times out after 30s; rejects files over 50MB.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "url": {"type": "string"},
            "parent_path": {"type": "string"},
        },
        "required": ["name", "url"],
    },
)


@register(import_step_spec, write=True)
async def run_import_step(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    name = a.get("name", "")
    url = a.get("url", "")
    parent_path = a.get("parent_path", "/")

    if not name or not url:
        return err_payload("name and url are required", "BAD_ARGS")

    if not url.startswith("https://"):
        return err_payload("url scheme must be https", "BAD_ARGS")

    parent_clean, err = normalize_path(parent_path)
    if err:
        return err_payload(err, "BAD_ARGS")

    parent_id = None
    if parent_clean != "/":
        rp = await resolve_path(ctx, parent_clean)
        if not rp.get("exists"):
            return err_payload("parent_path not found", "NOT_FOUND")
        if rp.get("kind") != "folder":
            return err_payload("parent_path is not a folder", "BAD_KIND")
        parent_id = rp["id"]

    leaf_path = parent_clean if parent_clean.endswith("/") else parent_clean + "/"
    leaf_path += name
    existing = await resolve_path(ctx, leaf_path)
    if existing.get("exists"):
        return err_payload(f"a file already exists at {leaf_path}", "EXISTS")

    import asyncio
    import httpx
    try:
        async with asyncio.timeout(30):
            response = await ctx.http_client.get(url, follow_redirects=True)
    except Exception as e:
        return err_payload(f"download failed: {e}", "DOWNLOAD")

    if response.status_code >= 400:
        return err_payload(f"download {response.status_code}", "DOWNLOAD")

    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > 50 * 1024 * 1024:
        return err_payload("file too large (>50MB)", "TOO_LARGE")

    content = response.content
    if len(content) > 50 * 1024 * 1024:
        return err_payload("file too large (>50MB)", "TOO_LARGE")

    import re
    safe_name = re.sub(r'[^\w\-.]', '_', name)
    key = f"projects/{ctx.project_id}/assets/{uuid.uuid4()}-{safe_name}"

    content_type = response.headers.get("content-type", "model/step")
    if content_type == "application/octet-stream":
        content_type = "model/step"

    size = len(content)

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content, storage_key, mime_type, size) VALUES ($1, $2, $3, 'step', '', $4, $5, $6) RETURNING id",
        ctx.project_id, parent_id, name, key, content_type, size,
    )

    return ok_payload({"path": leaf_path, "id": str(new_id), "size": size})


# ---------------------------------------------------------------------------
# KiCad import tool
# ---------------------------------------------------------------------------

import_kicad_spec = ToolSpec(
    name="import_kicad",
    description=(
        "Import a KiCad schematic or PCB project into the current project. "
        "Accepts the path to a .kicad_sch file or a project directory containing "
        ".kicad_sch / .kicad_pcb files. Returns extracted components, nets, and footprints."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Absolute path to a .kicad_sch file or directory containing KiCad project files.",
            },
        },
        "required": ["project_path"],
    },
)


@register(import_kicad_spec, write=False)
async def run_import_kicad(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    project_path = a.get("project_path", "").strip()
    if not project_path:
        return err_payload("project_path is required", "BAD_ARGS")

    import os
    import httpx

    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{pyworker_url}/import-kicad",
                json={"project_path": project_path},
            )
        if resp.status_code != 200:
            return err_payload(f"pyworker error {resp.status_code}: {resp.text[:300]}", "ERROR")
        data = resp.json()
    except Exception as e:
        return err_payload(f"failed to reach pyworker: {e}", "ERROR")

    errors = data.get("errors") or []
    if errors:
        return err_payload(errors[0], "ERROR")

    return ok_payload({
        "circuit_json": data.get("circuit_json", "{}"),
        "warnings": data.get("warnings", []),
    })
