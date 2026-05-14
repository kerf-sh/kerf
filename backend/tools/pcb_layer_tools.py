import json
import re
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

BOARD_TAG_PATTERN = re.compile(
    r'(<board\b[^>]*?)(\blayer_stack\s*=\s*(\{[^}]*\}|\[[^\]]*\]))?',
    re.DOTALL,
)

LAYER_STACK_EXPR_RE = re.compile(
    r'\blayer_stack\s*=\s*(\{[^}]*\}|\[[^\]]*\])',
    re.DOTALL,
)

BOARD_TAG_WITH_LS_RE = re.compile(
    r'(<board\b[^>]*?)\blayer_stack\s*=\s*(\{[^}]*\}|\[[^\]]*\])([^>]*>)',
    re.DOTALL,
)

PCB_ELEMENT_LAYER_RE = re.compile(
    r'(\<(?:pcb_component|pcb_trace|pcb_via|pcb_padstack|pcb_plated_pad|pcb_smt_pad)\b[^>]*\blayer\s*=\s*)(["\'])([^"\']*)\2([^>]*>)',
    re.DOTALL,
)

VALID_COPPER_COUNTS = {2, 4, 6, 8, 10, 12, 16, 20, 24, 30}


def _build_copper_layer_names(n):
    """Return ordered copper layer name list for n-layer board."""
    inner_count = max(0, n - 2)
    return ['top_copper'] + [f'inner_{i}' for i in range(1, inner_count + 1)] + ['bottom_copper']


LAYER_COUNTS = {n: _build_copper_layer_names(n) for n in VALID_COPPER_COUNTS}

# Legacy aliases
COPPER_LAYERS_2 = LAYER_COUNTS[2]
COPPER_LAYERS_4 = LAYER_COUNTS[4]
COPPER_LAYERS_6 = LAYER_COUNTS[6]
COPPER_LAYERS_8 = LAYER_COUNTS[8]

DEFAULT_LS_ENTRY = {
    'name': '',
    'type': 'copper',
    'color': '#64748b',
    'visible': True,
    'sublayer_order': 0,
}


def _default_color_for(name):
    defaults = {
        'top_copper': '#ef4444',
        'top_silk': '#f0f0f0',
        'top_mask': '#22c55e',
        'top_paste': '#a3a3a3',
        'bottom_copper': '#3b82f6',
        'bottom_silk': '#f0f0f0',
        'bottom_mask': '#22c55e',
        'bottom_paste': '#a3a3a3',
        'drill_plated': '#fbbf24',
        'drill_nonplated': '#fbbf24',
        'edge_cuts': '#64748b',
        'courtyard': '#64748b',
        'fab_notes': '#64748b',
    }
    for k, v in defaults.items():
        if name.startswith(k):
            return v
    return '#64748b'


def _parse_layer_stack(content):
    m = BOARD_TAG_WITH_LS_RE.search(content)
    if not m:
        return None
    try:
        return json.loads(m.group(2))
    except Exception:
        return None


def _format_layer_entry(name, type_, color, visible, order):
    return {
        'name': name,
        'type': type_,
        'color': color,
        'visible': visible,
        'sublayer_order': order,
    }


def _build_layer_stack_entries(sublayers):
    return [
        _format_layer_entry(sublayers[0], 'copper', '#ef4444', True, 0),
        _format_layer_entry('top_silk', 'silkscreen', '#f0f0f0', True, 1),
        _format_layer_entry('top_mask', 'soldermask', '#22c55e', True, 2),
        _format_layer_entry('top_paste', 'paste', '#a3a3a3', True, 3),
        _format_layer_entry(sublayers[-1], 'copper', '#3b82f6', True, 4),
        _format_layer_entry('bottom_silk', 'silkscreen', '#f0f0f0', True, 5),
        _format_layer_entry('bottom_mask', 'soldermask', '#22c55e', True, 6),
        _format_layer_entry('bottom_paste', 'paste', '#a3a3a3', True, 7),
        _format_layer_entry('drill_plated', 'drill', '#fbbf24', True, 8),
        _format_layer_entry('drill_nonplated', 'drill', '#fbbf24', True, 9),
        _format_layer_entry('edge_cuts', 'mechanical', '#64748b', True, 10),
        _format_layer_entry('courtyard', 'mechanical', '#64748b', True, 11),
        _format_layer_entry('fab_notes', 'mechanical', '#64748b', True, 12),
    ]


def _inject_layer_stack(content, layer_stack):
    ls_json = json.dumps(layer_stack, separators=(',', ':'))
    m = BOARD_TAG_WITH_LS_RE.search(content)
    if m:
        return content[:m.start()] + m.group(1) + f' layer_stack={ls_json}' + m.group(3) + content[m.end():]
    board_m = re.search(r'<board\b', content)
    if board_m:
        ins = board_m.start() + len('<board')
        return content[:ins] + f' layer_stack={ls_json}' + content[ins:]
    return content


def _layer_stack_with_entry(content, new_entry):
    ls = _parse_layer_stack(content)
    if ls is None:
        ls = _build_layer_stack_entries(['top_copper', 'bottom_copper'])
    for l in ls:
        if l.get('name') == new_entry.get('name'):
            return None, 'layer already exists'
    max_order = max((l.get('sublayer_order', 0) for l in ls), default=-1)
    entry = {**DEFAULT_LS_ENTRY, **new_entry, 'sublayer_order': max_order + 1}
    ls.append(entry)
    new_content = _inject_layer_stack(content, ls)
    return new_content, None


def _layer_stack_without_name(content, name):
    ls = _parse_layer_stack(content)
    if ls is None:
        return None, 'no layer_stack found'
    before = len(ls)
    ls = [l for l in ls if l.get('name') != name]
    if len(ls) == before:
        return None, f'layer {name} not found'
    ls = _reindex(ls)
    new_content = _inject_layer_stack(content, ls)
    return new_content, None


def _reindex(layers):
    for i, l in enumerate(layers):
        l['sublayer_order'] = i
    return layers


def _find_and_update_layer(content, name, updater):
    ls = _parse_layer_stack(content)
    if ls is None:
        return None, 'no layer_stack found'
    found = False
    for l in ls:
        if l.get('name') == name:
            updater(l)
            found = True
    if not found:
        return None, f'layer {name} not found'
    ls = _reindex(ls)
    new_content = _inject_layer_stack(content, ls)
    return new_content, None


def _move_layer_by_name(content, name, new_index):
    ls = _parse_layer_stack(content)
    if ls is None:
        return None, 'no layer_stack found'
    idx = next((i for i, l in enumerate(ls) if l.get('name') == name), None)
    if idx is None:
        return None, f'layer {name} not found'
    new_index = max(0, min(new_index, len(ls) - 1))
    if idx == new_index:
        return content, None
    ls.insert(new_index, ls.pop(idx))
    ls = _reindex(ls)
    new_content = _inject_layer_stack(content, ls)
    return new_content, None


def _update_element_layer(content, element_id, layer_name):
    pattern = re.compile(
        r'(<pcb_(?:component|trace|via|padstack|plated_pad|smt_pad)\b[^>]*\bid\s*=\s*(["\'])([^"\']*)\2[^>]*)\blayer\s*=\s*(["\'])([^"\']*)\4',
        re.DOTALL,
    )

    def replacer(m):
        if m.group(3) == element_id:
            return m.group(1) + f' layer={m.group(4)}{layer_name}{m.group(4)}' + m.group(6)
        return m.group(0)

    new_content, count = pattern.subn(replacer, content)
    if count == 0:
        return None, f'element with id {element_id} not found'
    return new_content, None


add_pcb_layer_spec = ToolSpec(
    name="add_pcb_layer",
    description="Add a new layer entry to board.layer_stack in a .circuit.tsx file. The layer is appended at the bottom of the stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "type": {"type": "string", "enum": ["copper", "silkscreen", "soldermask", "paste", "drill", "mechanical"]},
            "color": {"type": "string"},
        },
        "required": ["file_content", "name"],
    },
)


@register(add_pcb_layer_spec, write=True)
async def run_add_pcb_layer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_content = a.get("file_content", "")
    name = a.get("name", "")
    type_ = a.get("type", "mechanical")
    color = a.get("color") or _default_color_for(name)

    if not name:
        return err_payload("name is required", "BAD_ARGS")

    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    new_entry = {
        'name': name,
        'type': type_,
        'color': color,
        'visible': True,
        'sublayer_order': 0,
    }
    new_content, err = _layer_stack_with_entry(file_content, new_entry)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer '{name}' added"})


remove_pcb_layer_spec = ToolSpec(
    name="remove_pcb_layer",
    description="Remove a layer by name from board.layer_stack in a .circuit.tsx file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
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

    file_content = a.get("file_content", "")
    name = a.get("name", "")

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    new_content, err = _layer_stack_without_name(file_content, name)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer '{name}' removed"})


set_layer_visibility_spec = ToolSpec(
    name="set_layer_visibility",
    description="Toggle the visible flag for a named layer in board.layer_stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "visible": {"type": "boolean"},
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

    file_content = a.get("file_content", "")
    name = a.get("name", "")
    visible = bool(a.get("visible"))

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    def updater(l):
        l['visible'] = visible

    new_content, err = _find_and_update_layer(file_content, name, updater)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer '{name}' visibility set to {visible}"})


set_layer_color_spec = ToolSpec(
    name="set_layer_color",
    description="Set the color (hex) for a named layer in board.layer_stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "color": {"type": "string"},
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

    file_content = a.get("file_content", "")
    name = a.get("name", "")
    color = a.get("color", "")

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")
    if not color:
        return err_payload("color is required", "BAD_ARGS")

    def updater(l):
        l['color'] = color

    new_content, err = _find_and_update_layer(file_content, name, updater)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer '{name}' color set to {color}"})


reorder_layers_spec = ToolSpec(
    name="reorder_layers",
    description="Move a layer by name to a new position (index) in the board.layer_stack order.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "new_index": {"type": "integer"},
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

    file_content = a.get("file_content", "")
    name = a.get("name", "")
    new_index = int(a.get("new_index", 0))

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    new_content, err = _move_layer_by_name(file_content, name, new_index)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer '{name}' moved to index {new_index}"})


assign_to_layer_spec = ToolSpec(
    name="assign_to_layer",
    description="Update the layer field of a pcb_component, pcb_trace, or pcb_via element by its id in a .circuit.tsx file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "element_id": {"type": "string"},
            "layer_name": {"type": "string"},
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

    file_content = a.get("file_content", "")
    element_id = a.get("element_id", "")
    layer_name = a.get("layer_name", "")

    if not element_id or not layer_name:
        return err_payload("element_id and layer_name are required", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    new_content, err = _update_element_layer(file_content, element_id, layer_name)
    if err:
        return err_payload(err, "LAYER_ERROR")
    return ok_payload({"success": True, "updated_content": new_content, "message": f"element '{element_id}' assigned to layer '{layer_name}'"})


set_board_layer_count_spec = ToolSpec(
    name="set_board_layer_count",
    description=(
        "Set the total number of copper layers on the board. "
        "Valid values: 2, 4, 6, 8, 10, 12, 16, 20, 24, 30. "
        "Inner copper layers (inner_N) are auto-created between top_copper and bottom_copper, "
        "preserving any existing color overrides. Updates board.layer_stack accordingly."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "layer_count": {"type": "integer", "enum": sorted(VALID_COPPER_COUNTS)},
        },
        "required": ["file_content", "layer_count"],
    },
)


@register(set_board_layer_count_spec, write=True)
async def run_set_board_layer_count(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_content = a.get("file_content", "")
    layer_count = int(a.get("layer_count", 2))

    if layer_count not in VALID_COPPER_COUNTS:
        return err_payload(f"layer_count must be one of {sorted(VALID_COPPER_COUNTS)}", "BAD_ARGS")
    if not file_content:
        return err_payload("file_content is required", "BAD_ARGS")

    ls = _parse_layer_stack(file_content)
    existing_copper = [l for l in (ls or []) if l.get('type') == 'copper']
    existing_copper_names = set(l.get('name', '') for l in existing_copper)

    new_copper_layers = LAYER_COUNTS.get(layer_count, COPPER_LAYERS_2)
    new_copper_names = set(new_copper_layers)

    if ls is None:
        ls = _build_layer_stack_entries(new_copper_layers)
        new_content = _inject_layer_stack(file_content, ls)
        return ok_payload({"success": True, "updated_content": new_content, "message": f"layer_count set to {layer_count}; layer_stack created"})

    non_copper = [l for l in ls if l.get('type') != 'copper']

    copper_entries = []
    for i, name in enumerate(new_copper_layers):
        existing = next((l for l in existing_copper if l.get('name') == name), None)
        if existing:
            copper_entries.append({**existing, 'sublayer_order': i})
        else:
            copper_entries.append({
                'name': name,
                'type': 'copper',
                'color': _default_color_for(name),
                'visible': True,
                'sublayer_order': i,
            })

    merged = copper_entries + non_copper
    for i, l in enumerate(merged):
        l['sublayer_order'] = i

    new_content = _inject_layer_stack(file_content, merged)
    return ok_payload({"success": True, "updated_content": new_content, "message": f"layer_count set to {layer_count}; copper layers updated"})


# ─── PCB-prefixed tool aliases ────────────────────────────────────────────────
# These are the canonical names exposed to the LLM for PCB layer operations.
# They delegate to the same implementation as the un-prefixed versions above.

set_pcb_layer_visibility_spec = ToolSpec(
    name="set_pcb_layer_visibility",
    description="Toggle the visible flag for a named PCB layer in board.layer_stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "visible": {"type": "boolean"},
        },
        "required": ["file_content", "name", "visible"],
    },
)


@register(set_pcb_layer_visibility_spec, write=True)
async def run_set_pcb_layer_visibility(ctx: ProjectCtx, args: bytes) -> str:
    return await run_set_layer_visibility(ctx, args)


set_pcb_layer_color_spec = ToolSpec(
    name="set_pcb_layer_color",
    description="Set the color (hex string, e.g. '#ef4444') for a named PCB layer in board.layer_stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "color": {"type": "string"},
        },
        "required": ["file_content", "name", "color"],
    },
)


@register(set_pcb_layer_color_spec, write=True)
async def run_set_pcb_layer_color(ctx: ProjectCtx, args: bytes) -> str:
    return await run_set_layer_color(ctx, args)


reorder_pcb_layers_spec = ToolSpec(
    name="reorder_pcb_layers",
    description="Move a PCB layer by name to a new 0-based position in board.layer_stack.",
    input_schema={
        "type": "object",
        "properties": {
            "file_content": {"type": "string"},
            "name": {"type": "string"},
            "new_index": {"type": "integer"},
        },
        "required": ["file_content", "name", "new_index"],
    },
)


@register(reorder_pcb_layers_spec, write=True)
async def run_reorder_pcb_layers(ctx: ProjectCtx, args: bytes) -> str:
    return await run_reorder_layers(ctx, args)
