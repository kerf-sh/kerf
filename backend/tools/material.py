import json
import re
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


def parse_material_content(s: str) -> dict:
    if not s or not s.strip():
        return {"version": 1, "mechanical": {}, "thermal": {}, "physical": {}}
    try:
        d = json.loads(s)
    except Exception:
        return {"version": 1, "mechanical": {}, "thermal": {}, "physical": {}}
    if d.get("version", 0) == 0:
        d["version"] = 1
    if "common_names" not in d or d["common_names"] is None:
        d["common_names"] = []
    return d


read_material_spec = ToolSpec(
    name="read_material",
    description="Read a .material engineering-property file by absolute path. Returns the parsed JSON shape with mechanical / thermal / physical groups.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
)


@register(read_material_spec)
async def run_read_material(ctx: ProjectCtx, args: bytes) -> str:
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

    kind = rp.get("kind")
    name = rp.get("name", "")
    if kind != "material" and not name.lower().endswith(".material"):
        return err_payload(f"path is not a .material file (kind={kind})", "BAD_KIND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    content = row["content"] if row and row["content"] else ""

    doc = parse_material_content(content)

    return ok_payload({
        "path": path,
        "id": str(rp["id"]),
        "material": doc,
    })


find_material_by_name_spec = ToolSpec(
    name="find_material_by_name",
    description="Fuzzy-search every .material file in the project by name + common_names. Returns up to N matches (default 5, capped at 25).",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max": {"type": "integer"},
        },
        "required": ["query"],
    },
)


def score_material(q: str, doc: dict) -> tuple:
    q = q.lower().strip()
    if not q:
        return 0, ""

    name = doc.get("name", "").lower()
    common_names = [cn.lower() for cn in doc.get("common_names", [])]

    if name == q:
        return 1000, doc.get("name", "")
    for cn in common_names:
        if cn == q:
            return 800, cn
    if name.startswith(q):
        return 500, doc.get("name", "")
    for cn in common_names:
        if cn.startswith(q):
            return 400, cn
    if q in name:
        s = 300 - len(name) // 4
        if s < 1:
            s = 1
        return s, doc.get("name", "")
    for cn in common_names:
        if q in cn:
            s = 200 - len(cn) // 4
            if s < 1:
                s = 1
            return s, cn
    return 0, ""


@register(find_material_by_name_spec)
async def run_find_material_by_name(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    query = a.get("query", "").strip()
    if not query:
        return err_payload("query is required", "BAD_ARGS")

    max_matches = a.get("max", 5)
    if max_matches <= 0:
        max_matches = 5
    if max_matches > 25:
        max_matches = 25

    rows = await ctx.pool.fetch(
        "SELECT id, content FROM files WHERE project_id = $1 AND kind = 'material' AND deleted_at IS NULL",
        ctx.project_id,
    )

    matches = []
    for row in rows:
        doc = parse_material_content(row["content"] or "")
        score, hit = score_material(query, doc)
        if score == 0:
            continue
        path = await path_from_file_id(ctx, row["id"])
        matches.append({
            "path": path,
            "id": str(row["id"]),
            "name": doc.get("name", ""),
            "category": doc.get("category", ""),
            "score": score,
            "matched_name": hit,
        })

    matches.sort(key=lambda x: (-x["score"], x["name"]))
    if len(matches) > max_matches:
        matches = matches[:max_matches]

    return ok_payload({
        "query": query,
        "matches": matches,
    })


set_part_material_spec = ToolSpec(
    name="set_part_material",
    description="Attach a material to a Part by setting its `material_path` field. Both paths are absolute. Validates that material_path resolves to a kind='material' file before writing.",
    input_schema={
        "type": "object",
        "properties": {
            "part_path": {"type": "string"},
            "material_path": {"type": "string"},
        },
        "required": ["part_path", "material_path"],
    },
)


@register(set_part_material_spec, write=True)
async def run_set_part_material(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    part_path = a.get("part_path", "").strip()
    material_path = a.get("material_path", "").strip()

    if not part_path:
        return err_payload("part_path is required", "BAD_ARGS")

    part_rp = await resolve_path(ctx, part_path)
    if not part_rp.get("exists"):
        return err_payload(f"part file not found: {part_path}", "NOT_FOUND")

    if part_rp.get("kind") != "part":
        return err_payload(f"part_path is not a .part file (kind={part_rp.get('kind')})", "BAD_KIND")

    if material_path:
        mat_rp = await resolve_path(ctx, material_path)
        if not mat_rp.get("exists"):
            return err_payload(f"material file not found: {material_path}", "NOT_FOUND")
        if mat_rp.get("kind") != "material":
            return err_payload(f"material_path is not a .material file (kind={mat_rp.get('kind')})", "BAD_KIND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        part_rp["id"], ctx.project_id,
    )
    content = row["content"] if row and row["content"] else ""

    if not content or not content.strip():
        doc = {"version": 1}
    else:
        try:
            doc = json.loads(content)
        except Exception:
            doc = {"version": 1}

    if not isinstance(doc, dict):
        doc = {"version": 1}

    if material_path == "":
        if "material_path" in doc:
            del doc["material_path"]
    else:
        doc["material_path"] = material_path

    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, part_rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, part_rp["id"], body, "tool")

    return ok_payload({
        "part_path": part_path,
        "part_id": str(part_rp["id"]),
        "material_path": material_path,
        "cleared": material_path == "",
    })