"""
view.py — LLM tools for the .view.json saved-view system.

A view captures a named slice of a BIM model: plan, section, elevation, or 3d.
Views live as files with kind='view' inside the project tree.
"""

import json
import uuid as _uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.bim import ensure_folders, record_revision_for_file, resolve_path

# ── constants ──────────────────────────────────────────────────────────────────

VALID_KINDS = {'plan', 'section', 'elevation', '3d'}


# ── pure helpers ───────────────────────────────────────────────────────────────

def _default_view(name: str, kind: str, bim_file_id: str) -> dict:
    return {
        "version": 1,
        "name": name,
        "kind": kind,
        "bim_file_id": bim_file_id,
        "level_id": None,
        "cut_plane_z_mm": None,
        "section_origin": None,
        "section_direction": None,
        "crop_box": None,
        "filters": [],
        "display_overrides": {"by_category": {}},
        "annotations": [],
    }


def _validate_view(doc: dict) -> list[str]:
    errors = []
    if doc.get("version") != 1:
        errors.append("version must be 1")
    if doc.get("kind") not in VALID_KINDS:
        errors.append(f"kind must be one of {sorted(VALID_KINDS)}")
    if not doc.get("bim_file_id"):
        errors.append("bim_file_id is required")
    if not isinstance(doc.get("filters"), list):
        errors.append("filters must be a list")
    if not isinstance(doc.get("annotations"), list):
        errors.append("annotations must be a list")
    return errors


def _eval_expr(expr: str, element: dict) -> bool:
    """Simple filter expression evaluator: field==value, >, <, >=, <=, AND, OR."""
    if not expr:
        return True
    expr = expr.strip()

    # OR (split on first OR at top level)
    or_parts = expr.split(' OR ')
    if len(or_parts) > 1:
        return any(_eval_expr(p, element) for p in or_parts)

    and_parts = expr.split(' AND ')
    if len(and_parts) > 1:
        return all(_eval_expr(p, element) for p in and_parts)

    import re
    cmp = re.match(r"^(\w+)\s*(>=|<=|!=|>|<|==)\s*(?:'([^']*)'|(\S+))$", expr)
    if not cmp:
        return True
    field, op, quoted_val, raw_val = cmp.group(1), cmp.group(2), cmp.group(3), cmp.group(4)
    rhs = quoted_val if quoted_val is not None else raw_val
    lhs = element.get(field)
    if lhs is None:
        return False
    lhs_str = str(lhs)
    try:
        lhs_n, rhs_n = float(lhs), float(rhs)
        numeric = True
    except (TypeError, ValueError):
        lhs_n, rhs_n, numeric = None, None, False

    if op == '==':  return lhs_str == rhs
    if op == '!=':  return lhs_str != rhs
    if op == '>':   return (lhs_n > rhs_n) if numeric else (lhs_str > rhs)
    if op == '<':   return (lhs_n < rhs_n) if numeric else (lhs_str < rhs)
    if op == '>=':  return (lhs_n >= rhs_n) if numeric else (lhs_str >= rhs)
    if op == '<=':  return (lhs_n <= rhs_n) if numeric else (lhs_str <= rhs)
    return True


def run_view_filters(view_doc: dict, bim_doc: dict | None) -> list[dict]:
    """Return elements from bim_doc that pass all filters in view_doc."""
    if not bim_doc or not isinstance(bim_doc.get("elements"), list):
        return []
    filters = view_doc.get("filters", [])
    if not filters:
        return list(bim_doc["elements"])
    result = []
    for el in bim_doc["elements"]:
        visible = True
        for f in filters:
            expr = f if isinstance(f, str) else f.get("expr", "")
            if not _eval_expr(expr, el):
                visible = False
                break
        if visible:
            result.append(el)
    return result


# ── create_view ────────────────────────────────────────────────────────────────

create_view_spec = ToolSpec(
    name="create_view",
    description=(
        "Create a new .view.json file inside the project. "
        "kind must be 'plan', 'section', 'elevation', or '3d'. "
        "path must end with .view.json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path":           {"type": "string",  "description": "Absolute project path ending in .view.json"},
            "name":           {"type": "string"},
            "kind":           {"type": "string",  "enum": list(VALID_KINDS)},
            "bim_file_id":    {"type": "string",  "description": "UUID of the linked .bim file"},
            "level_id":       {"type": "string"},
            "cut_plane_z_mm": {"type": "number"},
        },
        "required": ["path", "name", "kind", "bim_file_id"],
    },
)


@register(create_view_spec, write=True)
async def run_create_view(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")
    kind = a.get("kind", "")
    bim_file_id = a.get("bim_file_id", "")

    if not path.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")
    if not path.endswith(".view.json"):
        return err_payload("path must end with .view.json", "BAD_KIND")

    rp = await resolve_path(ctx, path)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = _default_view(name, kind, bim_file_id)
    if a.get("level_id"):
        doc["level_id"] = a["level_id"]
    if a.get("cut_plane_z_mm") is not None:
        doc["cut_plane_z_mm"] = a["cut_plane_z_mm"]

    errs = _validate_view(doc)
    if errs:
        return err_payload("; ".join(errs), "VALIDATION_ERROR")

    body = json.dumps(doc, indent="  ")
    parts = [p for p in path.strip("/").split("/") if p]
    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) "
        "VALUES ($1, $2, $3, 'view', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")
    return ok_payload({"path": path, "id": str(new_id)})


# ── set_view_filters ───────────────────────────────────────────────────────────

set_view_filters_spec = ToolSpec(
    name="set_view_filters",
    description="Replace the filter list on an existing .view.json file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .view.json file"},
            "filters": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "object", "properties": {"expr": {"type": "string"}}, "required": ["expr"]},
                    ]
                },
            },
        },
        "required": ["file_id", "filters"],
    },
)


@register(set_view_filters_spec, write=True)
async def run_set_view_filters(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    filters = a.get("filters", [])

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'view' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("view file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("view file is not valid JSON", "PARSE_ERROR")

    doc["filters"] = filters
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
        body, fid,
    )
    await record_revision_for_file(ctx, fid, body, "tool")
    return ok_payload({"file_id": file_id, "filter_count": len(filters)})


# ── add_view_annotation ────────────────────────────────────────────────────────

add_view_annotation_spec = ToolSpec(
    name="add_view_annotation",
    description="Attach a tag, dimension, or leader annotation to a .view.json file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id":    {"type": "string"},
            "kind":       {"type": "string", "description": "door_tag | linear_dim | leader | spot_elev"},
            "element_id": {"type": "string"},
            "from":       {"type": "array",  "items": {"type": "number"}},
            "to":         {"type": "array",  "items": {"type": "number"}},
            "label":      {"type": "string"},
            "position":   {"type": "array",  "items": {"type": "number"}},
        },
        "required": ["file_id", "kind"],
    },
)


@register(add_view_annotation_spec, write=True)
async def run_add_view_annotation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'view' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("view file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("view file is not valid JSON", "PARSE_ERROR")

    ann_id = str(_uuid.uuid4())
    ann = {"id": ann_id, "kind": a.get("kind", "")}
    for key in ("element_id", "from", "to", "label", "position"):
        if key in a:
            ann[key] = a[key]

    doc.setdefault("annotations", []).append(ann)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
        body, fid,
    )
    await record_revision_for_file(ctx, fid, body, "tool")
    return ok_payload({"file_id": file_id, "annotation_id": ann_id})


# ── run_view ───────────────────────────────────────────────────────────────────

run_view_spec = ToolSpec(
    name="run_view",
    description=(
        "Resolve a .view.json's filters against the linked .bim file and return "
        "the list of visible elements."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .view.json file"},
        },
        "required": ["file_id"],
    },
)


@register(run_view_spec, write=False)
async def run_run_view(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    view_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'view' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not view_row:
        return err_payload("view file not found", "NOT_FOUND")

    try:
        view_doc = json.loads(view_row["content"])
    except Exception:
        return err_payload("view file is not valid JSON", "PARSE_ERROR")

    bim_file_id = view_doc.get("bim_file_id")
    if not bim_file_id:
        return err_payload("view has no linked bim_file_id", "NO_BIM")

    try:
        bim_fid = _uuid.UUID(bim_file_id)
    except Exception:
        return err_payload("bim_file_id in view is not a valid UUID", "BAD_ARGS")

    bim_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'bim' AND deleted_at IS NULL",
        bim_fid, ctx.project_id,
    )
    if not bim_row:
        return err_payload("linked bim file not found", "NOT_FOUND")

    try:
        bim_doc = json.loads(bim_row["content"])
    except Exception:
        return err_payload("bim file is not valid JSON", "PARSE_ERROR")

    visible = run_view_filters(view_doc, bim_doc)
    return ok_payload({"visible_count": len(visible), "elements": visible})
