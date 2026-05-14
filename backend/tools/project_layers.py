"""
Project-level layer + display-mode LLM tools.

All tools operate on the project's `.canvas.json` file (kind='canvas'),
creating it at the project root if it does not yet exist.
"""

import json
import re
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ---------------------------------------------------------------------------
# Default canvas (mirrors projectLayers.js defaultCanvas())
# ---------------------------------------------------------------------------

def _default_canvas() -> dict:
    return {
        "version": 1,
        "layers": [
            {
                "id": "L01",
                "name": "Geometry",
                "visible": True,
                "color": "#ffffff",
                "linetype": "continuous",
                "material_id": None,
                "locked": False,
            }
        ],
        "display_modes": [
            {"id": "shaded",    "name": "Shaded",    "wireframe": False, "edges": True,  "shadows": False, "transparency": 1.0,  "background_color": "#1a1a1a"},
            {"id": "wireframe", "name": "Wireframe", "wireframe": True,  "edges": True},
            {"id": "technical", "name": "Technical", "wireframe": False, "edges": True,  "silhouette": True, "shadows": False},
            {"id": "rendered",  "name": "Rendered",  "wireframe": False, "edges": False, "shadows": True,  "transparency": 0.95},
        ],
        "active_display_mode": "shaded",
        "active_layer": "L01",
    }

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$')


def _next_layer_id(layers: list[dict]) -> str:
    existing = {l["id"] for l in layers}
    n = len(layers) + 1
    while True:
        cid = f"L{n:02d}"
        if cid not in existing:
            return cid
        n += 1


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _load_canvas(ctx: ProjectCtx) -> tuple[uuid.UUID | None, dict]:
    """Return (file_id | None, canvas_dict). file_id is None if not yet saved."""
    row = await ctx.pool.fetchrow(
        "SELECT id, content FROM files "
        "WHERE project_id = $1 AND name = '.canvas.json' AND deleted_at IS NULL "
        "LIMIT 1",
        ctx.project_id,
    )
    if not row:
        return None, _default_canvas()
    try:
        canvas = json.loads(row["content"] or "{}")
        if not isinstance(canvas, dict) or "layers" not in canvas:
            canvas = _default_canvas()
    except Exception:
        canvas = _default_canvas()
    return row["id"], canvas


async def _save_canvas(ctx: ProjectCtx, file_id: uuid.UUID | None, canvas: dict) -> uuid.UUID:
    """Upsert the .canvas.json file; return its file_id."""
    content = json.dumps(canvas, indent=2)
    if file_id is None:
        new_id = uuid.uuid4()
        await ctx.pool.execute(
            "INSERT INTO files(id, project_id, parent_id, name, kind, content) "
            "VALUES ($1, $2, NULL, '.canvas.json', 'canvas', $3)",
            new_id, ctx.project_id, content,
        )
        return new_id
    else:
        await ctx.pool.execute(
            "UPDATE files SET content = $1, updated_at = NOW() WHERE id = $2",
            content, file_id,
        )
        return file_id


# ---------------------------------------------------------------------------
# Tool: create_layer
# ---------------------------------------------------------------------------

create_layer_spec = ToolSpec(
    name="create_layer",
    description=(
        "Create a new project layer. "
        "color must be a hex string like '#ff0000'. "
        "If a layer with the same name already exists the call is a no-op."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "name":       {"type": "string"},
            "color":      {"type": "string", "default": "#aaaaaa"},
            "linetype":   {"type": "string", "default": "continuous"},
            "locked":     {"type": "boolean", "default": False},
        },
        "required": ["project_id", "name"],
    },
)


@register(create_layer_spec, write=True)
async def run_create_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    name = a.get("name", "").strip()
    if not name:
        return err_payload("name is required", "BAD_ARGS")

    color    = a.get("color", "#aaaaaa")
    linetype = a.get("linetype", "continuous")
    locked   = bool(a.get("locked", False))

    if not _HEX_RE.match(color):
        return err_payload(f"invalid color: {color}", "BAD_ARGS")

    file_id, canvas = await _load_canvas(ctx)
    if any(l["name"] == name for l in canvas["layers"]):
        return ok_payload({"message": f"layer '{name}' already exists — no-op"})

    new_id = _next_layer_id(canvas["layers"])
    canvas["layers"].append({
        "id": new_id, "name": name, "visible": True,
        "color": color, "linetype": linetype,
        "material_id": None, "locked": locked,
    })
    await _save_canvas(ctx, file_id, canvas)
    return ok_payload({"layer_id": new_id, "message": f"created layer '{name}' as {new_id}"})


# ---------------------------------------------------------------------------
# Tool: delete_layer
# ---------------------------------------------------------------------------

delete_layer_spec = ToolSpec(
    name="delete_layer",
    description="Delete a project layer by id. Refuses if it is the last layer.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "layer_id":   {"type": "string"},
        },
        "required": ["project_id", "layer_id"],
    },
)


@register(delete_layer_spec, write=True)
async def run_delete_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    layer_id = a.get("layer_id", "").strip()
    if not layer_id:
        return err_payload("layer_id is required", "BAD_ARGS")

    file_id, canvas = await _load_canvas(ctx)
    filtered = [l for l in canvas["layers"] if l["id"] != layer_id]
    if len(filtered) == len(canvas["layers"]):
        return ok_payload({"message": f"layer '{layer_id}' not found — no-op"})
    if len(filtered) == 0:
        return err_payload("cannot remove the last layer", "PROTECTED")

    canvas["layers"] = filtered
    if canvas.get("active_layer") == layer_id:
        canvas["active_layer"] = filtered[0]["id"]

    await _save_canvas(ctx, file_id, canvas)
    return ok_payload({"message": f"deleted layer '{layer_id}'"})


# ---------------------------------------------------------------------------
# Tool: set_layer_visibility
# ---------------------------------------------------------------------------

set_layer_visibility_spec = ToolSpec(
    name="set_project_layer_visibility",
    description="Show or hide a project layer.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "layer_id":   {"type": "string"},
            "visible":    {"type": "boolean"},
        },
        "required": ["project_id", "layer_id", "visible"],
    },
)


@register(set_layer_visibility_spec, write=True)
async def run_set_layer_visibility(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    layer_id = a.get("layer_id", "").strip()
    visible  = bool(a.get("visible", True))

    file_id, canvas = await _load_canvas(ctx)
    found = False
    for l in canvas["layers"]:
        if l["id"] == layer_id:
            l["visible"] = visible
            found = True
            break
    if not found:
        return err_payload(f"layer '{layer_id}' not found", "NOT_FOUND")

    await _save_canvas(ctx, file_id, canvas)
    return ok_payload({"message": f"set '{layer_id}' visible={visible}"})


# ---------------------------------------------------------------------------
# Tool: set_layer_color
# ---------------------------------------------------------------------------

set_layer_color_spec = ToolSpec(
    name="set_project_layer_color",
    description="Set the hex color of a project layer.",
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "layer_id":   {"type": "string"},
            "color":      {"type": "string", "description": "Hex color e.g. '#ff0000'"},
        },
        "required": ["project_id", "layer_id", "color"],
    },
)


@register(set_layer_color_spec, write=True)
async def run_set_layer_color(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    layer_id = a.get("layer_id", "").strip()
    color    = a.get("color", "").strip()

    if not _HEX_RE.match(color):
        return err_payload(f"invalid color: {color}", "BAD_ARGS")

    file_id, canvas = await _load_canvas(ctx)
    found = False
    for l in canvas["layers"]:
        if l["id"] == layer_id:
            l["color"] = color
            found = True
            break
    if not found:
        return err_payload(f"layer '{layer_id}' not found", "NOT_FOUND")

    await _save_canvas(ctx, file_id, canvas)
    return ok_payload({"message": f"set '{layer_id}' color={color}"})


# ---------------------------------------------------------------------------
# Tool: assign_to_layer
# ---------------------------------------------------------------------------

assign_to_layer_spec = ToolSpec(
    name="assign_file_to_layer",
    description=(
        "Record which layer a project file belongs to. "
        "Stores the layer_id in the file's metadata JSON under key 'layer_id'. "
        "The file must belong to the same project."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "file_id":    {"type": "string", "description": "UUID of the file to assign"},
            "layer_id":   {"type": "string"},
        },
        "required": ["project_id", "file_id", "layer_id"],
    },
)


@register(assign_to_layer_spec, write=True)
async def run_assign_to_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_file_id = a.get("file_id", "").strip()
    layer_id    = a.get("layer_id", "").strip()

    if not raw_file_id or not layer_id:
        return err_payload("file_id and layer_id are required", "BAD_ARGS")

    try:
        target_file_id = uuid.UUID(raw_file_id)
    except ValueError:
        return err_payload(f"invalid file_id UUID: {raw_file_id}", "BAD_ARGS")

    # Verify the layer exists in canvas.
    _, canvas = await _load_canvas(ctx)
    if not any(l["id"] == layer_id for l in canvas["layers"]):
        return err_payload(f"layer '{layer_id}' not found in canvas", "NOT_FOUND")

    # Verify file belongs to project.
    row = await ctx.pool.fetchrow(
        "SELECT id, metadata FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        target_file_id, ctx.project_id,
    )
    if not row:
        return err_payload(f"file '{raw_file_id}' not found in project", "NOT_FOUND")

    existing_meta = {}
    if row["metadata"]:
        try:
            existing_meta = json.loads(row["metadata"])
        except Exception:
            pass
    existing_meta["layer_id"] = layer_id

    await ctx.pool.execute(
        "UPDATE files SET metadata = $1, updated_at = NOW() WHERE id = $2",
        json.dumps(existing_meta), target_file_id,
    )
    return ok_payload({"message": f"assigned file '{raw_file_id}' to layer '{layer_id}'"})


# ---------------------------------------------------------------------------
# Tool: switch_display_mode
# ---------------------------------------------------------------------------

switch_display_mode_spec = ToolSpec(
    name="switch_display_mode",
    description=(
        "Set the active display mode for the project's 3D viewport. "
        "Built-in modes: shaded | wireframe | technical | rendered."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "mode_id":    {"type": "string", "description": "Display mode id, e.g. 'wireframe'"},
        },
        "required": ["project_id", "mode_id"],
    },
)


@register(switch_display_mode_spec, write=True)
async def run_switch_display_mode(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    mode_id = a.get("mode_id", "").strip()
    if not mode_id:
        return err_payload("mode_id is required", "BAD_ARGS")

    file_id, canvas = await _load_canvas(ctx)
    if not any(m["id"] == mode_id for m in canvas["display_modes"]):
        valid = [m["id"] for m in canvas["display_modes"]]
        return err_payload(f"mode '{mode_id}' not found; valid: {valid}", "NOT_FOUND")

    canvas["active_display_mode"] = mode_id
    await _save_canvas(ctx, file_id, canvas)
    return ok_payload({"message": f"active display mode set to '{mode_id}'"})
