"""
sheet.py — LLM tools for the .sheet.json print-ready layout system.

A sheet is a print-ready composition: paper size, title block, and viewports
that each reference a .view.json file. Sheets live with kind='sheet'.
"""

import json
import uuid as _uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.bim import ensure_folders, record_revision_for_file, resolve_path

# ── constants ──────────────────────────────────────────────────────────────────

SHEET_SIZES_MM = {
    "A0":     [841,  1189],
    "A1":     [594,   841],
    "A2":     [420,   594],
    "A3":     [297,   420],
    "A4":     [210,   297],
    "ANSI_A": [216,   279],
    "ANSI_B": [279,   432],
    "ANSI_C": [432,   559],
    "ANSI_D": [559,   864],
    "ANSI_E": [864,  1118],
}

VALID_SIZES = set(SHEET_SIZES_MM.keys())
VALID_ORIENTATIONS = {"landscape", "portrait"}


# ── pure helpers ───────────────────────────────────────────────────────────────

def _default_sheet(name: str, sheet_number: str, size: str) -> dict:
    return {
        "version": 1,
        "name": name,
        "sheet_number": sheet_number,
        "size": size,
        "orientation": "landscape",
        "titleblock": {
            "project_name": "",
            "issue_date": "",
            "revision": "",
            "drawn_by": "",
        },
        "viewports": [],
        "revision_clouds": [],
    }


def _validate_sheet(doc: dict) -> list[str]:
    errors = []
    if doc.get("version") != 1:
        errors.append("version must be 1")
    if not doc.get("name"):
        errors.append("name is required")
    if not doc.get("sheet_number"):
        errors.append("sheet_number is required")
    if doc.get("size") not in VALID_SIZES:
        errors.append(f"size must be one of {sorted(VALID_SIZES)}")
    if doc.get("orientation") not in VALID_ORIENTATIONS:
        errors.append(f"orientation must be one of {sorted(VALID_ORIENTATIONS)}")
    if not isinstance(doc.get("viewports"), list):
        errors.append("viewports must be a list")
    if not isinstance(doc.get("revision_clouds"), list):
        errors.append("revision_clouds must be a list")
    return errors


# ── create_sheet ───────────────────────────────────────────────────────────────

create_sheet_spec = ToolSpec(
    name="create_sheet",
    description=(
        "Create a new .sheet.json layout file inside the project. "
        "path must end with .sheet.json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path":         {"type": "string",  "description": "Absolute project path ending in .sheet.json"},
            "name":         {"type": "string"},
            "sheet_number": {"type": "string"},
            "size":         {"type": "string",  "enum": sorted(VALID_SIZES)},
            "orientation":  {"type": "string",  "enum": sorted(VALID_ORIENTATIONS)},
        },
        "required": ["path", "name", "sheet_number", "size"],
    },
)


@register(create_sheet_spec, write=True)
async def run_create_sheet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")
    sheet_number = a.get("sheet_number", "")
    size = a.get("size", "")

    if not path.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")
    if not path.endswith(".sheet.json"):
        return err_payload("path must end with .sheet.json", "BAD_KIND")

    rp = await resolve_path(ctx, path)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = _default_sheet(name, sheet_number, size)
    if a.get("orientation"):
        doc["orientation"] = a["orientation"]

    errs = _validate_sheet(doc)
    if errs:
        return err_payload("; ".join(errs), "VALIDATION_ERROR")

    body = json.dumps(doc, indent="  ")
    parts = [p for p in path.strip("/").split("/") if p]
    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) "
        "VALUES ($1, $2, $3, 'sheet', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")
    return ok_payload({"path": path, "id": str(new_id)})


# ── add_viewport_to_sheet ──────────────────────────────────────────────────────

add_viewport_spec = ToolSpec(
    name="add_viewport_to_sheet",
    description="Add a viewport referencing a .view.json file to an existing .sheet.json.",
    input_schema={
        "type": "object",
        "properties": {
            "sheet_file_id": {"type": "string", "description": "UUID of the .sheet.json file"},
            "view_file_id":  {"type": "string", "description": "UUID of the .view.json file"},
            "position":      {"type": "array",  "items": {"type": "number"}, "description": "[x, y] in mm"},
            "scale":         {"type": "number", "description": "e.g. 0.02 for 1:50"},
            "title":         {"type": "string"},
        },
        "required": ["sheet_file_id", "view_file_id", "position", "scale"],
    },
)


@register(add_viewport_spec, write=True)
async def run_add_viewport(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    sheet_file_id = a.get("sheet_file_id", "")
    view_file_id  = a.get("view_file_id",  "")
    position      = a.get("position",      [])
    scale         = a.get("scale",         0)

    try:
        sfid = _uuid.UUID(sheet_file_id)
    except Exception:
        return err_payload("sheet_file_id must be a valid UUID", "BAD_ARGS")

    if not isinstance(position, list) or len(position) < 2:
        return err_payload("position must be a [x, y] array", "BAD_ARGS")
    if not isinstance(scale, (int, float)) or scale <= 0:
        return err_payload("scale must be a positive number", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'sheet' AND deleted_at IS NULL",
        sfid, ctx.project_id,
    )
    if not row:
        return err_payload("sheet file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("sheet file is not valid JSON", "PARSE_ERROR")

    vp_id = str(_uuid.uuid4())
    vp = {
        "id":           vp_id,
        "view_file_id": view_file_id,
        "position":     position,
        "scale":        scale,
        "title":        a.get("title", ""),
    }
    doc.setdefault("viewports", []).append(vp)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
        body, sfid,
    )
    await record_revision_for_file(ctx, sfid, body, "tool")
    return ok_payload({"sheet_file_id": sheet_file_id, "viewport_id": vp_id})


# ── remove_viewport ────────────────────────────────────────────────────────────

remove_viewport_spec = ToolSpec(
    name="remove_viewport",
    description="Remove a viewport from a .sheet.json file by its id.",
    input_schema={
        "type": "object",
        "properties": {
            "sheet_file_id": {"type": "string"},
            "viewport_id":   {"type": "string"},
        },
        "required": ["sheet_file_id", "viewport_id"],
    },
)


@register(remove_viewport_spec, write=True)
async def run_remove_viewport(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    sheet_file_id = a.get("sheet_file_id", "")
    viewport_id   = a.get("viewport_id",   "")

    try:
        sfid = _uuid.UUID(sheet_file_id)
    except Exception:
        return err_payload("sheet_file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'sheet' AND deleted_at IS NULL",
        sfid, ctx.project_id,
    )
    if not row:
        return err_payload("sheet file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("sheet file is not valid JSON", "PARSE_ERROR")

    before = len(doc.get("viewports", []))
    doc["viewports"] = [vp for vp in doc.get("viewports", []) if vp.get("id") != viewport_id]
    removed = before - len(doc["viewports"])

    body = json.dumps(doc, indent="  ")
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
        body, sfid,
    )
    await record_revision_for_file(ctx, sfid, body, "tool")
    return ok_payload({"sheet_file_id": sheet_file_id, "removed": removed})


# ── add_revision_cloud ─────────────────────────────────────────────────────────

add_revision_cloud_spec = ToolSpec(
    name="add_revision_cloud",
    description="Add a revision cloud annotation to a .sheet.json file.",
    input_schema={
        "type": "object",
        "properties": {
            "sheet_file_id": {"type": "string"},
            "polygon":       {"type": "array",  "description": "List of [x,y] points (min 3)"},
            "revision":      {"type": "string", "description": "Revision label e.g. 'A'"},
            "note":          {"type": "string"},
        },
        "required": ["sheet_file_id", "polygon", "revision"],
    },
)


@register(add_revision_cloud_spec, write=True)
async def run_add_revision_cloud(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    sheet_file_id = a.get("sheet_file_id", "")
    polygon       = a.get("polygon",       [])
    revision      = a.get("revision",      "")

    try:
        sfid = _uuid.UUID(sheet_file_id)
    except Exception:
        return err_payload("sheet_file_id must be a valid UUID", "BAD_ARGS")

    if not isinstance(polygon, list) or len(polygon) < 3:
        return err_payload("polygon must be a list of at least 3 [x,y] points", "BAD_ARGS")
    if not revision:
        return err_payload("revision is required", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'sheet' AND deleted_at IS NULL",
        sfid, ctx.project_id,
    )
    if not row:
        return err_payload("sheet file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("sheet file is not valid JSON", "PARSE_ERROR")

    cloud_id = str(_uuid.uuid4())
    cloud = {"id": cloud_id, "polygon": polygon, "revision": revision, "note": a.get("note", "")}
    doc.setdefault("revision_clouds", []).append(cloud)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
        body, sfid,
    )
    await record_revision_for_file(ctx, sfid, body, "tool")
    return ok_payload({"sheet_file_id": sheet_file_id, "cloud_id": cloud_id})
