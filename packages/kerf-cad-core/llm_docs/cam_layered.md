# cam_layered — Layered Cross-Section Stacker

Generate a `.cam.layered` document from a solid by stacking plane cross-sections at fixed
Z (or X/Y) intervals.  Produces one 2-D contour per layer using OCCT
`BRepAlgoAPI_Section`.  **Not** G-code — downstream `cam_contour` wraps layers into
G-code with Z-step retracts.

---

## When to use

Keywords: layered milling, waterjet layers, laser stack, stacked cross-sections,
cam layered, section stack, layered cam, z-step, slice solid, contour slices,
layered contour, layer milling strategy.

---

## Entrypoints

### `validate_cam_layered_args(target_solid_ref, z_step_mm, z_start_mm, z_end_mm, axis) -> tuple[str|None, str|None]`

Pure validation.  Returns `(error_msg, error_code)` or `(None, None)` on success.

---

### `build_cam_layered_node(node_id, target_solid_ref, z_step_mm, z_start_mm, z_end_mm, axis, name) -> dict`

Build the feature-node dict without writing to the DB.

Returns:
```json
{
  "id": "cam-layered-1",
  "op": "cam_layered",
  "target_solid_ref": "pad-1",
  "z_step_mm": 5.0,
  "axis": "Z"
}
```
`z_start_mm` and `z_end_mm` are omitted when `None` (worker auto-detects from bbox).

---

### `compute_layers(shape, axis, z_step_mm, z_start_mm, z_end_mm) -> list`

Section a `TopoDS_Shape` at fixed intervals.  OCC-gated (returns `[]` if pythonOCC absent).

Returns:
```json
[
  { "z_mm": 0.0, "edges": [[[x0,y0],[x1,y1]], ...] },
  { "z_mm": 5.0, "edges": [...] }
]
```

Layers that produce no edges (e.g. exactly at a face boundary) are silently omitted.

---

### `build_cam_layered_result(shape, axis, z_step_mm, z_start_mm, z_end_mm) -> dict`

Full `.cam.layered` document:
```json
{
  "version": 1,
  "axis": "Z",
  "z_step_mm": 5.0,
  "layers": [...]
}
```

---

## LLM tool

**Name:** `feature_cam_layered`

**Required args:** `file_id` (UUID), `target_solid_ref` (node id), `z_step_mm` (positive number)

**Optional args:** `z_start_mm`, `z_end_mm`, `axis` (`"Z"`|`"X"`|`"Y"`, default `"Z"`), `name`, `id`

**Writes** the feature node to the file and attempts the OCC section stack.  Returns:
```json
{
  "file_id": "...",
  "id": "cam-layered-1",
  "op": "cam_layered",
  "axis": "Z",
  "z_step_mm": 5.0,
  "layer_count": 10,
  "layers": { "version": 1, "axis": "Z", "z_step_mm": 5.0, "layers": [...] }
}
```

If OCC is unavailable or the section fails, a `warning` key is added and `layers` is
omitted — the node is still written so the worker can re-evaluate when OCC is present.

---

## Axis conventions

| `axis` | Slicing planes | 2-D coordinate pair |
|---|---|---|
| `Z` (default) | XY-parallel planes at each z_mm | `[x, y]` |
| `X` | YZ-parallel planes | `[y, z]` |
| `Y` | XZ-parallel planes | `[x, z]` |

---

## Usage snippet

```python
# Via LLM tool (agent usage)
# {
#   "tool": "feature_cam_layered",
#   "file_id": "3f2a...",
#   "target_solid_ref": "pad-1",
#   "z_step_mm": 5.0,
#   "axis": "Z"
# }

# Direct Python
from kerf_cad_core.cam_layered import build_cam_layered_node, compute_layers

node = build_cam_layered_node("cam-1", "pad-1", 5.0, None, None, "Z")
# node["op"] == "cam_layered"
```

---

## Caveats

- Feature-tree evaluator in `_eval_feature_tree_to_node` supports `pad`, `boolean`, and
  `section` ops only; complex op trees may return an approximate bounding-box proxy.
  Accurate layers require a fully supported feature tree.
- G-code generation is out of scope — use `cam_contour` after this step.
- `z_start_mm` / `z_end_mm` are auto-detected from the OCCT bounding box when omitted.
