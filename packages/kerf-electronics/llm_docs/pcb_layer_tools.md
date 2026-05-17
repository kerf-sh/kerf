# kerf-electronics · pcb_layer_tools.py

PCB layer stack management for `.circuit.tsx` files. All tools operate on
`board.layer_stack` — a JSON array embedded in the `<board ... layer_stack=...>`
tag.

## LLM tools

All tools accept and return `file_content` (the full `.circuit.tsx` string).

### `add_pcb_layer`

Append a new layer entry to the layer stack.

```json
{
  "file_content": "<board ... />",
  "name": "power_plane",
  "type": "copper",
  "color": "#f59e0b"
}
```

Layer `type` values: `copper`, `silkscreen`, `soldermask`, `paste`, `drill`, `mechanical`.

Returns: `{success, updated_content, message}`.

### `remove_pcb_layer`

Remove a layer by name.

```json
{"file_content": "...", "name": "power_plane"}
```

### `set_pcb_layer_visibility` / `set_layer_visibility`

Toggle a layer's `visible` flag.

```json
{"file_content": "...", "name": "bottom_silk", "visible": false}
```

### `set_pcb_layer_color` / `set_layer_color`

Set a layer's display colour (hex string).

```json
{"file_content": "...", "name": "top_copper", "color": "#ef4444"}
```

### `reorder_pcb_layers` / `reorder_layers`

Move a layer to a new 0-based index position.

```json
{"file_content": "...", "name": "power_plane", "new_index": 2}
```

### `assign_to_layer`

Update the `layer` attribute of a `pcb_component`, `pcb_trace`, or
`pcb_via` element by its `id`.

```json
{
  "file_content": "...",
  "element_id": "trace_abc12",
  "layer_name": "bottom_copper"
}
```

### `set_board_layer_count`

Set the total copper layer count. Auto-creates inner copper layers
(`inner_1`, `inner_2`, …) between `top_copper` and `bottom_copper`.

Valid counts: 2, 4, 6, 8, 10, 12, 16, 20, 24, 30.

```json
{"file_content": "...", "layer_count": 4}
```

Existing color overrides for `top_copper`/`bottom_copper` are preserved.

## Layer naming conventions

| Layer name | Type | Default colour |
|---|---|---|
| `top_copper` | copper | #ef4444 (red) |
| `inner_N` (N=1..n-2) | copper | #64748b |
| `bottom_copper` | copper | #3b82f6 (blue) |
| `top_silk` | silkscreen | #f0f0f0 |
| `bottom_silk` | silkscreen | #f0f0f0 |
| `top_mask` | soldermask | #22c55e |
| `bottom_mask` | soldermask | #22c55e |
| `top_paste` | paste | #a3a3a3 |
| `bottom_paste` | paste | #a3a3a3 |
| `drill_plated` | drill | #fbbf24 |
| `drill_nonplated` | drill | #fbbf24 |
| `edge_cuts` | mechanical | #64748b |
| `courtyard` | mechanical | #64748b |
| `fab_notes` | mechanical | #64748b |

## Note on aliases

`set_pcb_layer_visibility`, `set_pcb_layer_color`, `reorder_pcb_layers` are
canonical PCB-prefixed aliases that delegate to the un-prefixed variants.
Both sets are registered.

## Standards reference

- IPC-2581B: Printed Circuit Assembly Data Exchange Format (layer stack)
- IPC-7351C: Generic Requirements for Surface Mount Design and Land Pattern Standard
