import json
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def _get_nested_value(obj, path):
    if not path:
        return None
    keys = path.split(".")
    value = obj
    for key in keys:
        if value is None or not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _apply_filter(element, f):
    field_value = _get_nested_value(element, f["field"])
    filter_value = f["value"]
    op = f["op"]

    if op == "eq":
        return field_value == filter_value
    elif op == "ne":
        return field_value != filter_value
    elif op == "gt":
        return field_value is not None and filter_value is not None and field_value > filter_value
    elif op == "lt":
        return field_value is not None and filter_value is not None and field_value < filter_value
    elif op == "gte":
        return field_value is not None and filter_value is not None and field_value >= filter_value
    elif op == "lte":
        return field_value is not None and filter_value is not None and field_value <= filter_value
    elif op == "in":
        return field_value in filter_value if isinstance(filter_value, list) else False
    elif op == "contains":
        if isinstance(field_value, str):
            return filter_value in field_value
        if isinstance(field_value, list):
            return filter_value in field_value
        return False
    return True


def _get_elements_by_category(bim_doc, category):
    if not bim_doc:
        return []
    elements = bim_doc.get("elements", [])
    plural_map = {
        "Wall": "walls",
        "Door": "doors",
        "Window": "windows",
        "Room": "rooms",
        "Slab": "slabs",
        "Space": "spaces",
        "Opening": "openings",
        "Level": "levels",
        "Site": "site",
    }
    key = plural_map.get(category)
    if not key:
        return []
    if category == "Site":
        return [bim_doc["site"]] if bim_doc.get("site") else []
    return [
        el for el in elements
        if _get_nested_value(el, "category") == category or el.get("type") == category
    ]


def _sort_rows(rows, sort_by):
    if not sort_by:
        return rows
    parts = sort_by.split(":")
    field = parts[0]
    direction = parts[1] if len(parts) > 1 else "asc"
    reverse = direction == "desc"
    return sorted(rows, key=lambda r: _get_nested_value(r, field) or "", reverse=reverse)


def _apply_group_by(rows, group_by):
    if not group_by:
        return [[r] for r in rows]
    groups = {}
    for row in rows:
        key = _get_nested_value(row, group_by) or "(empty)"
        if key not in groups:
            groups[key] = []
        groups[key].append(row)
    return list(groups.values())


def run_schedule_py(schedule_doc, bim_doc):
    if not schedule_doc or not bim_doc:
        return {"columns": [], "rows": []}

    target_category = schedule_doc.get("target_category", "Wall")
    filters = schedule_doc.get("filters", [])
    columns = schedule_doc.get("columns", [])
    group_by = schedule_doc.get("group_by")
    sort_by = schedule_doc.get("sort_by")

    elements = _get_elements_by_category(bim_doc, target_category)

    for f in filters:
        elements = [el for el in elements if _apply_filter(el, f)]

    processed_rows = []
    for el in elements:
        row = {}
        for col in columns:
            value = _get_nested_value(el, col["field"])
            row[col["field"]] = value if value is not None else None
        processed_rows.append(row)

    sorted_rows = _sort_rows(processed_rows, sort_by)
    grouped_rows = _apply_group_by(sorted_rows, group_by)

    output_columns = [
        {
            "field": col["field"],
            "label": col.get("label") or col["field"],
            "format": col.get("format"),
        }
        for col in columns
    ]

    return {
        "columns": output_columns,
        "rows": grouped_rows,
    }


create_schedule_spec = ToolSpec(
    name="create_schedule",
    description="Create a new .schedule.json schedule definition file in the project tree.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "name": {"type": "string"},
            "target_category": {"type": "string", "enum": ["Wall", "Door", "Window", "Room", "Slab", "Space", "Opening", "Level", "Site"]},
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "label": {"type": "string"},
                        "format": {"type": "string"},
                    },
                    "required": ["field"],
                },
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "op": {"type": "string", "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains"]},
                        "value": {},
                    },
                    "required": ["field", "op", "value"],
                },
            },
            "group_by": {"type": "string"},
            "sort_by": {"type": "string"},
        },
        "required": ["path", "name", "target_category"],
    },
)


@register(create_schedule_spec, write=True)
async def run_create_schedule(ctx: ProjectCtx, args: bytes) -> str:
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

    from tools.bim import resolve_path, ensure_folders
    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    parts = [p for p in clean.strip("/").split("/") if p]
    parent_id = await ensure_folders(ctx, parts[:-1]) if len(parts) > 1 else None
    leaf = parts[-1] if parts else "schedule.schedule"

    schedule_doc = {
        "version": 1,
        "name": a.get("name", "Untitled Schedule"),
        "target_category": a.get("target_category", "Wall"),
        "filters": a.get("filters", []),
        "columns": a.get("columns", []),
        "group_by": a.get("group_by"),
        "sort_by": a.get("sort_by"),
    }

    body = json.dumps(schedule_doc, indent="  ")

    from tools.bim import record_revision_for_file
    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'schedule', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id)})


update_schedule_filter_spec = ToolSpec(
    name="update_schedule_filter",
    description="Update the filter on an existing .schedule.json file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "filter": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "op": {"type": "string", "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains"]},
                    "value": {},
                },
                "required": ["field", "op", "value"],
            },
        },
        "required": ["file_id", "filter"],
    },
)


@register(update_schedule_filter_spec, write=True)
async def run_update_schedule_filter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    import uuid
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("invalid file_id", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND id = $2 AND kind = 'schedule'",
        ctx.project_id, fid,
    )
    if not row:
        return err_payload("schedule file not found", "NOT_FOUND")

    content = row["content"] if row["content"] else "{}"
    try:
        schedule_doc = json.loads(content)
    except Exception:
        return err_payload("invalid schedule JSON", "BAD_ARGS")

    new_filter = a.get("filter")
    if new_filter:
        schedule_doc["filters"] = [new_filter]

    new_content = json.dumps(schedule_doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2",
        new_content, fid,
    )

    from tools.bim import record_revision_for_file
    await record_revision_for_file(ctx, fid, new_content, "tool")

    return ok_payload({"updated": True})


run_schedule_spec = ToolSpec(
    name="run_schedule",
    description="Execute a .schedule.json against a .bim file and return the table result.",
    input_schema={
        "type": "object",
        "properties": {
            "schedule_file_id": {"type": "string"},
            "bim_file_id": {"type": "string"},
        },
        "required": ["schedule_file_id", "bim_file_id"],
    },
)


@register(run_schedule_spec)
async def run_run_schedule(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    schedule_file_id = a.get("schedule_file_id", "")
    bim_file_id = a.get("bim_file_id", "")

    if not schedule_file_id or not bim_file_id:
        return err_payload("both schedule_file_id and bim_file_id are required", "BAD_ARGS")

    import uuid
    try:
        sched_fid = uuid.UUID(schedule_file_id)
        bim_fid = uuid.UUID(bim_file_id)
    except Exception:
        return err_payload("invalid file_id", "BAD_ARGS")

    sched_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND id = $2 AND kind = 'schedule'",
        ctx.project_id, sched_fid,
    )
    if not sched_row:
        return err_payload("schedule file not found", "NOT_FOUND")

    bim_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND id = $2 AND kind = 'bim'",
        ctx.project_id, bim_fid,
    )
    if not bim_row:
        return err_payload("bim file not found", "NOT_FOUND")

    try:
        schedule_doc = json.loads(sched_row["content"] or "{}")
        bim_doc = json.loads(bim_row["content"] or "{}")
    except Exception as e:
        return err_payload(f"failed to parse JSON: {e}", "BAD_ARGS")

    result = run_schedule_py(schedule_doc, bim_doc)
    return ok_payload(result)