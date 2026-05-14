# PCB Layer Stack

## Schema

A PCB board is represented in a `.circuit.tsx` file as a `<board … />` JSX element.  
The `layer_stack` prop holds a JSON array of layer objects:

```jsonc
[
  {
    "name": "top_copper",       // canonical layer name (string, unique)
    "type": "copper",           // "copper" | "silkscreen" | "soldermask" | "paste" | "drill" | "mechanical"
    "color": "#ef4444",         // display color (hex)
    "visible": true,            // shown in the PCB view
    "sublayer_order": 0         // render / stack position (0 = top)
  },
  …
]
```

### Canonical 2-layer board (default)

| Order | name              | type       |
|-------|-------------------|------------|
| 0     | top_copper        | copper     |
| 1     | top_silk          | silkscreen |
| 2     | top_mask          | soldermask |
| 3     | top_paste         | paste      |
| 4     | bottom_copper     | copper     |
| 5     | bottom_silk       | silkscreen |
| 6     | bottom_mask       | soldermask |
| 7     | bottom_paste      | paste      |
| 8     | drill_plated      | drill      |
| 9     | drill_nonplated   | drill      |
| 10    | edge_cuts         | mechanical |
| 11    | courtyard         | mechanical |
| 12    | fab_notes         | mechanical |

### Multi-layer boards

Inner copper layers follow the naming convention `inner_1`, `inner_2`, … `inner_{N-2}` and are
inserted between `top_copper` and `bottom_copper`.  
Valid copper layer counts: **2, 4, 6, 8, 10, 12, 16, 20, 24, 30** (same as KiCad).

A 4-layer board adds `inner_1` and `inner_2`:

```
top_copper → inner_1 → inner_2 → bottom_copper
```

---

## Tools

### `add_pcb_layer`
Append a new layer to `board.layer_stack`.

```json
{
  "file_content": "<board layer_stack=[…] />…",
  "name": "user_drawing",
  "type": "mechanical",
  "color": "#a78bfa"
}
```

Returns `{ "success": true, "updated_content": "…" }`.

---

### `remove_pcb_layer`
Remove a layer by name.

```json
{ "file_content": "…", "name": "user_drawing" }
```

Core layers (e.g. `top_copper`) can be removed but this will likely break the PCB renderer —
prefer `set_pcb_layer_visibility` to hide them instead.

---

### `set_pcb_layer_visibility`
Show or hide a layer without removing it.

```json
{ "file_content": "…", "name": "courtyard", "visible": false }
```

---

### `set_pcb_layer_color`
Change the display color of a layer (hex string).

```json
{ "file_content": "…", "name": "top_copper", "color": "#ff6b6b" }
```

---

### `reorder_pcb_layers`
Move a layer to a specific 0-based index.

```json
{ "file_content": "…", "name": "fab_notes", "new_index": 0 }
```

All other layers shift to maintain contiguous `sublayer_order` values.

---

### `set_board_layer_count`
Set the total copper layer count. Inner layers are auto-generated; existing color overrides
for surviving inner layers are preserved.

```json
{ "file_content": "…", "layer_count": 4 }
```

Valid `layer_count` values: 2, 4, 6, 8, 10, 12, 16, 20, 24, 30.

---

## Examples

### Hide the courtyard layer

```json
{
  "tool": "set_pcb_layer_visibility",
  "args": { "file_content": "…", "name": "courtyard", "visible": false }
}
```

### Upgrade from 2-layer to 4-layer

```json
{
  "tool": "set_board_layer_count",
  "args": { "file_content": "…", "layer_count": 4 }
}
```

The tool inserts `inner_1` and `inner_2` between `top_copper` and `bottom_copper` and
re-sequences `sublayer_order`.

### Add a user annotation layer

```json
{
  "tool": "add_pcb_layer",
  "args": {
    "file_content": "…",
    "name": "user_notes",
    "type": "mechanical",
    "color": "#fbbf24"
  }
}
```
