import gzip
import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def gunzip_bytes(b: bytes) -> str:
    if not b:
        return ""
    import io
    r = gzip.GzipFile(fileobj=io.BytesIO(b))
    out, _ = r.read()
    return out.decode()


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


async def reconstruct_revision(ctx: ProjectCtx, rev_id: uuid.UUID) -> str:
    row = await ctx.pool.fetchrow(
        "SELECT id, kind, parent_revision_id, content_gz, content FROM file_revisions WHERE id = $1",
        rev_id,
    )
    if not row:
        return ""

    kind = row["kind"]
    parent_id = row["parent_revision_id"]
    gz = row["content_gz"]
    plain = row["content"]

    chain = [{"kind": kind, "parent_id": parent_id, "gz": gz, "plain": plain}]
    while chain[0]["kind"] == "diff":
        pid = chain[0]["parent_id"]
        if pid is None:
            break
        prow = await ctx.pool.fetchrow(
            "SELECT id, kind, parent_revision_id, content_gz, content FROM file_revisions WHERE id = $1",
            pid,
        )
        if not prow:
            break
        chain.insert(0, {"kind": prow["kind"], "parent_id": prow["parent_revision_id"], "gz": prow["content_gz"], "plain": prow["content"]})

    current = ""
    if chain[0]["gz"]:
        current = gunzip_bytes(chain[0]["gz"])
    elif chain[0]["plain"]:
        current = chain[0]["plain"]

    for i in range(1, len(chain)):
        delta = ""
        if chain[i]["gz"]:
            delta = gunzip_bytes(chain[i]["gz"])
        elif chain[i]["plain"]:
            delta = chain[i]["plain"]

        diffs = compute_diff_delta(current, delta)
        current = apply_diff_delta(current, diffs)

    return current


def compute_diff_delta(parent: str, child: str) -> str:
    from difflib import unified_diff
    diff = list(unified_diff([parent], [child], lineterm=""))
    return "\n".join(diff)


def apply_diff_delta(parent: str, delta: str) -> str:
    import re
    lines = delta.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@', line)
            if m:
                old_start = int(m.group(1))
                old_count = int(m.group(2)) if m.group(2) else 1
                result.extend(parent.split("\n")[old_start - 1:old_start - 1 + old_count])
                i += 1
                while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("---"):
                    if lines[i].startswith("+") and not lines[i].startswith("+++"):
                        result.append(lines[i][1:])
                    i += 1
                continue
        i += 1
    return "\n".join(result)


async def write_revision(ctx: ProjectCtx, file_id: str, content: str, source: str) -> uuid.UUID:
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


list_revisions_spec = ToolSpec(
    name="list_revisions",
    description="List the most-recent edits to a file as a chronological history (newest first). Returns id, source ('user'|'tool'|'llm'|'restore'), created_at, and a 200-char content_preview per row.",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["file_path"],
    },
)


@register(list_revisions_spec)
async def run_list_revisions(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_path = a.get("file_path", "")
    limit = a.get("limit", 50)

    if not file_path:
        return err_payload("file_path is required", "BAD_ARGS")

    if limit <= 0:
        limit = 50
    if limit > 200:
        limit = 200

    rp = await resolve_path(ctx, file_path)
    if not rp.get("exists"):
        fid_row = await ctx.pool.fetchrow(
            "SELECT id FROM files WHERE project_id = $1 AND name = $2 AND deleted_at IS NOT NULL LIMIT 1",
            ctx.project_id, file_path,
        )
        if not fid_row:
            return err_payload(f"file not found: {file_path}", "NOT_FOUND")
        file_id = fid_row["id"]
    else:
        file_id = rp["id"]

    rows = await ctx.pool.fetch(
        """SELECT fr.id, fr.source, fr.user_id, u.name, fr.created_at,
                  COALESCE(fr.content_preview, LEFT(fr.content, 200))
           FROM file_revisions fr
           LEFT JOIN users u ON u.id = fr.user_id
           WHERE fr.file_id = $1
           ORDER BY fr.created_at DESC
           LIMIT $2""",
        file_id,
        limit,
    )

    revisions = []
    for row in rows:
        user_id_str = None
        if row["user_id"]:
            user_id_str = str(row["user_id"])
        user_name = row["name"] if row["name"] else None
        revisions.append({
            "id": str(row["id"]),
            "source": row["source"],
            "user_id": user_id_str,
            "user_name": user_name,
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "content_preview": row["coalesce"] or "",
        })

    return ok_payload({"revisions": revisions})


restore_revision_spec = ToolSpec(
    name="restore_revision",
    description="Restore a file to one of its previous revisions. Use list_revisions first to find the desired revision id. The restore is itself recorded as a new revision so it can be undone.",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "revision_id": {"type": "string"},
        },
        "required": ["file_path", "revision_id"],
    },
)


@register(restore_revision_spec, write=True)
async def run_restore_revision(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_path = a.get("file_path", "")
    revision_id_str = a.get("revision_id", "")

    if not file_path or not revision_id_str:
        return err_payload("file_path and revision_id are required", "BAD_ARGS")

    try:
        rev_id = uuid.UUID(revision_id_str)
    except Exception:
        return err_payload("invalid revision_id", "BAD_ARGS")

    rp = await resolve_path(ctx, file_path)
    if not rp.get("exists"):
        fid_row = await ctx.pool.fetchrow(
            "SELECT id FROM files WHERE project_id = $1 AND name = $2 AND deleted_at IS NOT NULL LIMIT 1",
            ctx.project_id, file_path,
        )
        if not fid_row:
            return err_payload(f"file not found: {file_path}", "NOT_FOUND")
        file_id = fid_row["id"]
    else:
        file_id = rp["id"]

    ok_row = await ctx.pool.fetchrow(
        """SELECT EXISTS(
            SELECT 1 FROM file_revisions fr
            INNER JOIN files f ON f.id = fr.file_id
            WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        )""",
        rev_id, file_id, ctx.project_id,
    )
    if not ok_row or not ok_row[0]:
        return err_payload("revision not found", "NOT_FOUND")

    content = await reconstruct_revision(ctx, rev_id)

    await ctx.pool.execute(
        "UPDATE files SET content = $1, deleted_at = NULL, updated_at = now() WHERE id = $2 AND project_id = $3",
        content, file_id, ctx.project_id,
    )

    cap = ctx.file_revisions_max if ctx.file_revisions_max > 0 else 200
    new_rev = await write_revision(ctx, str(file_id), content, "restore")

    return ok_payload({
        "path": file_path,
        "restored_revision_id": revision_id_str,
        "new_revision_id": str(new_rev),
    })