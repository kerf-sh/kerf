"""
PCB layer-stack LLM tools.

Each tool accepts the raw .circuit.tsx file content as `file_content` and
returns { success, updated_content, message } via ok_payload / err_payload.

Layer operations are text-level edits on the embedded CircuitJSON / TSX
source.  They look for a `pcb_board` object (or the board config JSX prop)
and patch it in-place using a regex-based JSON fragment replacement.
"""

import json
import re
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_LAYER_STACK = [
    {"name": "top_copper",      "type": "copper",     "color": "#ef4444", "visible": True,  "sublayer_order": 0},
    {"name": "top_silk",        "type": "silkscreen", "color": "#f0f0f0", "visible": True,  "sublayer_order": 1},
    {"name": "top_mask",        "type": "soldermask", "color": "#22c55e", "visible": True,  "sublayer_order": 2},
    {"name": "top_paste",       "type": "paste",      "color": "#a3a3a3", "visible": True,  "sublayer_order": 3},
    {"name": "bottom_copper",   "type": "copper",     "color": "#3b82f6", "visible": True,  "sublayer_order": 4},
    {"name": "bottom_silk",     "type": "silkscreen", "color": "#f0f0f0", "visible": True,  "sublayer_order": 5},
    {"name": "bottom_mask",     "type": "soldermask", "color": "#22c55e", "visible": True,  "sublayer_order": 6},
    {"name": "bottom_paste",    "type": "paste",      "color": "#a3a3a3", "visible": True,  "sublayer_order": 7},
    {"name": "drill_plated",    "type": "drill",      "color": "#fbbf24", "visible": True,  "sublayer_order": 8},
    {"name": "drill_nonplated", "type": "drill",      "color": "#fbbf24", "visible": True,  "sublayer_order": 9},
    {"name": "edge_cuts",       "type": "mechanical", "color": "#64748b", "visible": True,  "sublayer_order": 10},
    {"name": "courtyard",       "type": "mechanical", "color": "#64748b", "visible": True,  "sublayer_order": 11},
    {"name": "fab_notes",       "type": "mechanical", "color": "#64748b", "visible": True,  "sublayer_order": 12},
]

VALID_TYPES = {"copper", "silkscreen", "soldermask", "paste", "drill", "mechanical"}


def _build_inner_copper(n: int):
    """Return inner_1 … inner_{n-2} layer dicts for an n-layer board."""
    layers = []
    for i in range(1, n - 1):
        layers.append({
            "name": f"inner_{i}",
            "type": "copper",
            "color": "#a78bfa",
            "visible": True,
            "sublayer_order": i,
        })
    return layers


def _find_board_json_in_tsx(content: str):
    """
    Look for a JSON object that contains "type": "pcb_board" in the TSX
    source.  Returns (start_idx, end_idx, dict) or None.

    Strategy: scan for '"type":"pcb_board"' or '"type": "pcb_board"', then
    walk backwards to find the opening '{' and forward to find the matching '}'.
    """
    pattern = re.compile(r'"type"\s*:\s*"pcb_board"')
    m = pattern.search(content)
    if not m:
        return None

    # Walk backwards to find opening brace.
    start = m.start()
    depth = 0
    for i in range(start, -1, -1):
        if content[i] == '}':
            depth += 1
        elif content[i] == '{':
            if depth == 0:
                obj_start = i
                break
            depth -= 1
    else:
        return None

    # Walk forward to find matching closing brace.
    depth = 0
    for i in range(obj_start, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                obj_end = i + 1
                break
    else:
        return None

    try:
        obj = json.loads(content[obj_start:obj_end])
    except json.JSONDecodeError:
        return None

    return obj_start, obj_end, obj


def _patch_board_layer_stack(content: str, stack: list) -> tuple[bool, str]:
    """
    Replace or insert the layer_stack key inside the pcb_board JSON object.
    Returns (success, new_content).
    """
    result = _find_board_json_in_tsx(content)
    if result is None:
        # No pcb_board object found — append a minimal one.
        board_obj = {
            "type": "pcb_board",
            "width": 100,
            "height": 100,
            "layer_stack": stack,
        }
        snippet = "\n// PCB board configuration\nconst _board = " + json.dumps(board_obj, indent=2) + ";\n"
        return True, content + snippet

    start, end, obj = result
    obj["layer_stack"] = stack
    new_fragment = json.dumps(obj, indent=2)
    return True, content[:start] + new_fragment + content[end:]


def _get_board_layer_stack(content: str) -> list:
    result = _find_board_json_in_tsx(content)
    if result is None:
        return [dict(l) for l in DEFAULT_LAYER_STACK]
    _, _, obj = result
    stack = obj.get("layer_stack")
    if isinstance(stack, list) and stack:
        return stack
    return [dict(l) for l in DEFAULT_LAYER_STACK]


# ---------------------------------------------------------------------------
# Tool: add_pcb_layer
# ---------------------------------------------------------------------------

add_pcb_layer_spec = ToolSpec(
    name="add_pcb_layer",
    description=(
        "Add a layer to the PCB layer stack.  "
        "type must be one of: copper | silkscreen | soldermask | paste | drill | mechanical.  "
        "If the layer name already exists the call is a no-op."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name":         {"type": "string", "description": "Unique layer name, e.g. 'inner_3'"},
            "layer_type":   {"type": "string", "enum": list(VALID_TYPES)},
            "color":        {"type": "string", "description": "Hex color, e.g. '#a78bfa'"},
            "visible":      {"type": "boolean"},
        },
        "required": ["file_content", "name", "layer_type"],
    },
)


@register(add_pcb_layer_spec, write=True)
async def run_add_pcb_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    name = a.get("name", "").strip()
    layer_type = a.get("layer_type", "")
    color = a.get("color", "#64748b")
    visible = a.get("visible", True)

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if layer_type not in VALID_TYPES:
        return err_payload(f"layer_type must be one of {sorted(VALID_TYPES)}", "BAD_ARGS")

    stack = _get_board_layer_stack(content)
    if any(l["name"] == name for l in stack):
        return ok_payload({"updated_content": content, "message": f"layer '{name}' already exists — no-op"})

    new_layer = {
        "name": name,
        "type": layer_type,
        "color": color,
        "visible": visible,
        "sublayer_order": len(stack),
    }
    stack.append(new_layer)
    ok, new_content = _patch_board_layer_stack(content, stack)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")
    return ok_payload({"updated_content": new_content, "message": f"added layer '{name}'"})


# ---------------------------------------------------------------------------
# Tool: remove_pcb_layer
# ---------------------------------------------------------------------------

remove_pcb_layer_spec = ToolSpec(
    name="remove_pcb_layer",
    description="Remove a layer from the PCB layer stack by name.  Removing a built-in copper layer (top_copper, bottom_copper) is refused.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name":         {"type": "string"},
        },
        "required": ["file_content", "name"],
    },
)


@register(remove_pcb_layer_spec, write=True)
async def run_remove_pcb_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    name = a.get("name", "").strip()

    PROTECTED = {"top_copper", "bottom_copper"}
    if name in PROTECTED:
        return err_payload(f"cannot remove protected layer '{name}'", "PROTECTED")

    stack = _get_board_layer_stack(content)
    filtered = [l for l in stack if l["name"] != name]
    if len(filtered) == len(stack):
        return ok_payload({"updated_content": content, "message": f"layer '{name}' not found — no-op"})

    # Re-number sublayer_order.
    for i, l in enumerate(filtered):
        l["sublayer_order"] = i

    ok, new_content = _patch_board_layer_stack(content, filtered)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")
    return ok_payload({"updated_content": new_content, "message": f"removed layer '{name}'"})


# ---------------------------------------------------------------------------
# Tool: set_layer_visibility
# ---------------------------------------------------------------------------

set_layer_visibility_spec = ToolSpec(
    name="set_layer_visibility",
    description="Set the visible flag on a PCB layer.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name":         {"type": "string"},
            "visible":      {"type": "boolean"},
        },
        "required": ["file_content", "name", "visible"],
    },
)


@register(set_layer_visibility_spec, write=True)
async def run_set_layer_visibility(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    name = a.get("name", "").strip()
    visible = bool(a.get("visible", True))

    stack = _get_board_layer_stack(content)
    found = False
    for l in stack:
        if l["name"] == name:
            l["visible"] = visible
            found = True
            break
    if not found:
        return err_payload(f"layer '{name}' not found", "NOT_FOUND")

    ok, new_content = _patch_board_layer_stack(content, stack)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")
    return ok_payload({"updated_content": new_content, "message": f"set '{name}' visible={visible}"})


# ---------------------------------------------------------------------------
# Tool: set_layer_color
# ---------------------------------------------------------------------------

set_layer_color_spec = ToolSpec(
    name="set_layer_color",
    description="Set the color (hex) of a PCB layer.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name":         {"type": "string"},
            "color":        {"type": "string", "description": "Hex color, e.g. '#ff0000'"},
        },
        "required": ["file_content", "name", "color"],
    },
)


@register(set_layer_color_spec, write=True)
async def run_set_layer_color(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    name = a.get("name", "").strip()
    color = a.get("color", "#64748b")

    if not re.match(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$', color):
        return err_payload("color must be a valid hex string e.g. '#ef4444'", "BAD_ARGS")

    stack = _get_board_layer_stack(content)
    found = False
    for l in stack:
        if l["name"] == name:
            l["color"] = color
            found = True
            break
    if not found:
        return err_payload(f"layer '{name}' not found", "NOT_FOUND")

    ok, new_content = _patch_board_layer_stack(content, stack)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")
    return ok_payload({"updated_content": new_content, "message": f"set '{name}' color={color}"})


# ---------------------------------------------------------------------------
# Tool: reorder_layers
# ---------------------------------------------------------------------------

reorder_layers_spec = ToolSpec(
    name="reorder_layers",
    description="Move a PCB layer to a new index position in the layer stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name":         {"type": "string"},
            "new_index":    {"type": "integer", "minimum": 0},
        },
        "required": ["file_content", "name", "new_index"],
    },
)


@register(reorder_layers_spec, write=True)
async def run_reorder_layers(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    name = a.get("name", "").strip()
    new_index = int(a.get("new_index", 0))

    stack = _get_board_layer_stack(content)
    old_index = next((i for i, l in enumerate(stack) if l["name"] == name), None)
    if old_index is None:
        return err_payload(f"layer '{name}' not found", "NOT_FOUND")

    clamped = max(0, min(new_index, len(stack) - 1))
    moved = stack.pop(old_index)
    stack.insert(clamped, moved)
    for i, l in enumerate(stack):
        l["sublayer_order"] = i

    ok, new_content = _patch_board_layer_stack(content, stack)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")
    return ok_payload({"updated_content": new_content, "message": f"moved '{name}' to index {clamped}"})


# ---------------------------------------------------------------------------
# Tool: assign_to_layer
# ---------------------------------------------------------------------------

assign_to_layer_spec = ToolSpec(
    name="assign_to_layer",
    description=(
        "Update a component, trace, via or pour's layer field.  "
        "Targets the element by its id (pcb_component_id, pcb_trace_id, pcb_via_id, etc.)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_content":  {"type": "string"},
            "element_id":    {"type": "string"},
            "layer_name":    {"type": "string"},
        },
        "required": ["file_content", "element_id", "layer_name"],
    },
)


@register(assign_to_layer_spec, write=True)
async def run_assign_to_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    element_id = a.get("element_id", "").strip()
    layer_name = a.get("layer_name", "").strip()

    if not element_id or not layer_name:
        return err_payload("element_id and layer_name are required", "BAD_ARGS")

    # Simple text patch: find the element_id string and set/replace the "layer" key near it.
    # This is a best-effort heuristic for TSX source; a full AST approach is out of scope.
    id_pattern = re.compile(re.escape(f'"{element_id}"'))
    m = id_pattern.search(content)
    if not m:
        return err_payload(f"element_id '{element_id}' not found in file", "NOT_FOUND")

    # Look within 500 chars after the id for a "layer" key to replace.
    window = content[m.start():m.start() + 500]
    layer_re = re.compile(r'"layer"\s*:\s*"[^"]*"')
    lm = layer_re.search(window)
    if lm:
        replacement = f'"layer": "{layer_name}"'
        new_window = window[:lm.start()] + replacement + window[lm.end():]
        new_content = content[:m.start()] + new_window + content[m.start() + 500:]
    else:
        # Insert layer after the id.
        insert_at = m.end()
        new_content = content[:insert_at] + f', "layer": "{layer_name}"' + content[insert_at:]

    return ok_payload({"updated_content": new_content, "message": f"assigned '{element_id}' to layer '{layer_name}'"})


# ---------------------------------------------------------------------------
# Tool: set_board_layer_count
# ---------------------------------------------------------------------------

set_board_layer_count_spec = ToolSpec(
    name="set_board_layer_count",
    description=(
        "Set the total copper layer count (2, 4, 6, 8 …).  "
        "Automatically inserts inner_1 … inner_N-2 copper layers between "
        "top_copper and bottom_copper in the layer stack.  "
        "Minimum is 2 (top + bottom only)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_content":   {"type": "string"},
            "copper_count":   {"type": "integer", "minimum": 2, "multipleOf": 2},
        },
        "required": ["file_content", "copper_count"],
    },
)


@register(set_board_layer_count_spec, write=True)
async def run_set_board_layer_count(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    content = a.get("file_content", "")
    copper_count = int(a.get("copper_count", 2))
    if copper_count < 2:
        copper_count = 2

    stack = _get_board_layer_stack(content)

    # Strip any existing inner layers.
    non_inner = [l for l in stack if not l["name"].startswith("inner_")]

    # Find top_copper and bottom_copper positions.
    tc_idx = next((i for i, l in enumerate(non_inner) if l["name"] == "top_copper"), 0)
    bc_idx = next((i for i, l in enumerate(non_inner) if l["name"] == "bottom_copper"), len(non_inner) - 1)

    inners = _build_inner_copper(copper_count)
    # Insert inners after top_copper and before bottom_copper.
    new_stack = non_inner[:tc_idx + 1] + inners + non_inner[tc_idx + 1:]
    for i, l in enumerate(new_stack):
        l["sublayer_order"] = i

    ok, new_content = _patch_board_layer_stack(content, new_stack)
    if not ok:
        return err_payload("failed to patch board", "PATCH_FAIL")

    inner_names = [l["name"] for l in inners]
    msg = f"set board to {copper_count}-layer; added inners: {inner_names}" if inners else f"set board to 2-layer; no inner layers"
    return ok_payload({"updated_content": new_content, "message": msg})
