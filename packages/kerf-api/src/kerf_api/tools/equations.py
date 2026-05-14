import json
import re
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_core.revisions import write_revision as _write_revision


read_equations_spec = ToolSpec(
    name="read_equations",
    description="Read the project-level .equations parameter file. Returns the parsed JSON shape {version, params:[{name, expr, unit, comment}, ...]}. If no .equations file exists, returns an empty params array.",
    input_schema={"type": "object", "properties": {}},
)


async def find_equations_file(ctx: ProjectCtx) -> tuple:
    rows = await ctx.pool.fetch(
        "SELECT id, name FROM files WHERE project_id = $1 AND kind = 'equations' AND deleted_at IS NULL",
        ctx.project_id,
    )
    if not rows:
        return None, None
    files = [(r["id"], r["name"]) for r in rows]
    files.sort(key=lambda x: x[1])
    return files[0]


@register(read_equations_spec)
async def run_read_equations(ctx: ProjectCtx, args: bytes) -> str:
    file_id, name = await find_equations_file(ctx)
    if not file_id:
        return ok_payload({"exists": False, "version": 1, "params": []})

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        file_id, ctx.project_id,
    )
    content = row["content"] if row and row["content"] else ""

    doc = {"version": 1, "params": []}
    if content and content.strip():
        try:
            doc = json.loads(content)
        except Exception:
            pass

    return ok_payload({
        "exists": True,
        "path": "/" + name,
        "id": str(file_id),
        "version": doc.get("version", 1),
        "params": doc.get("params", []),
    })


set_equation_spec = ToolSpec(
    name="set_equation",
    description="Upsert a single named parameter in the project-level .equations file. Creates the file at /params.equations if none exists.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "expr": {"type": "string"},
            "unit": {"type": "string"},
            "comment": {"type": "string"},
        },
        "required": ["name", "expr"],
    },
)


def valid_ident(s: str) -> bool:
    if not s:
        return False
    for i, r in enumerate(s):
        is_letter = r.isalpha() or r == '_'
        is_digit = r.isdigit()
        if i == 0 and not is_letter:
            return False
        if i > 0 and not is_letter and not is_digit:
            return False
    return True


async def record_revision_for_file(ctx: ProjectCtx, file_id: uuid.UUID, content: str, source: str):
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


@register(set_equation_spec, write=True)
async def run_set_equation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    name = a.get("name", "").strip()
    expr = a.get("expr", "").strip()
    unit = a.get("unit", "")
    comment = a.get("comment", "")

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not expr:
        return err_payload("expr is required", "BAD_ARGS")
    if not valid_ident(name):
        return err_payload("name must be a valid identifier (letters/digits/underscore, no leading digit)", "BAD_ARGS")

    file_id, file_name = await find_equations_file(ctx)

    doc = {"version": 1, "params": []}
    if file_id:
        row = await ctx.pool.fetchrow(
            "SELECT content FROM files WHERE id = $1 AND project_id = $2",
            file_id, ctx.project_id,
        )
        content = row["content"] if row and row["content"] else ""
        if content and content.strip():
            try:
                doc = json.loads(content)
            except Exception:
                pass
        if doc.get("version", 0) == 0:
            doc["version"] = 1
        if "params" not in doc or doc["params"] is None:
            doc["params"] = []

    updated = False
    for p in doc["params"]:
        if p.get("name") == name:
            p["expr"] = expr
            p["unit"] = unit
            p["comment"] = comment
            updated = True
            break
    if not updated:
        doc["params"].append({
            "name": name,
            "expr": expr,
            "unit": unit,
            "comment": comment,
        })

    body = json.dumps(doc, indent="  ")

    if not file_id:
        new_id = await ctx.pool.fetchval(
            "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, null, 'params.equations', 'equations', $2) RETURNING id",
            ctx.project_id, body,
        )
        await record_revision_for_file(ctx, new_id, body, "tool")
        return ok_payload({
            "path": "/params.equations",
            "id": str(new_id),
            "created": True,
            "name": name,
        })

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, file_id, ctx.project_id,
    )
    await record_revision_for_file(ctx, file_id, body, "tool")
    return ok_payload({
        "path": "/" + file_name,
        "id": str(file_id),
        "created": False,
        "name": name,
        "updated": updated,
    })