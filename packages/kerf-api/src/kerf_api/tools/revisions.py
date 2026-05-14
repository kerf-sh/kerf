import json
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_core.revisions import (
    reconstruct_revision as _reconstruct_revision,
    write_revision as _write_revision,
)


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
    """Thin wrapper so callers in this module don't need to import kerf_core directly."""
    return await _reconstruct_revision(ctx.pool, rev_id)


async def write_revision(ctx: ProjectCtx, file_id: str, content: str, source: str) -> uuid.UUID:
    """Thin wrapper that threads ctx fields into the canonical implementation."""
    cap = ctx.file_revisions_max if ctx.file_revisions_max > 0 else 200
    user_id = ctx.user_id if ctx.user_id != uuid.UUID(int=0) else None
    return await _write_revision(
        pool=ctx.pool,
        file_id=file_id,
        content=content,
        source=source,
        user_id=user_id,
        cap=cap,
    )


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
                  COALESCE(fr.content_preview, LEFT(fr.content, 200)) AS content_preview
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
        user_id_str = str(row["user_id"]) if row["user_id"] else None
        user_name = row["name"] if row["name"] else None
        revisions.append({
            "id": str(row["id"]),
            "source": row["source"],
            "user_id": user_id_str,
            "user_name": user_name,
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "content_preview": row["content_preview"] or "",
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

    new_rev = await write_revision(ctx, str(file_id), content, "restore")

    return ok_payload({
        "path": file_path,
        "restored_revision_id": revision_id_str,
        "new_revision_id": str(new_rev),
    })
