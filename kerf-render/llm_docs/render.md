# Render Tools

LLM tools for producing render-quality output via Blender Cycles. A `.render` file is a
JSON scene description referencing existing geometry (feature, mesh, STEP). The pyworker
executes Blender headless and returns a PNG or EXR image.

## File format

```json
{
  "version": 1,
  "name": "Hero shot",
  "scene_file_id": "<uuid>",
  "camera": {
    "position": [3000, -3000, 2000],
    "target": [0, 0, 500],
    "up": [0, 0, 1],
    "fov_deg": 45,
    "type": "perspective"
  },
  "lights": [
    {"id": "key",  "kind": "sun",  "direction": [-1,-1,-2], "intensity": 5,  "color": "#ffffff"},
    {"id": "fill", "kind": "area", "position": [3000,2000,2000], "size_mm": 1000, "intensity": 2, "color": "#e8f0ff"},
    {"id": "back", "kind": "sun",  "direction": [1,0.5,-0.5],    "intensity": 1,  "color": "#fff0e0"}
  ],
  "materials_override": {
    "*": {"kind": "principled", "base_color": "#888888", "roughness": 0.5, "metallic": 0.0}
  },
  "environment": {"kind": "color", "color": "#202020"},
  "render_settings": {
    "resolution": [1920, 1080],
    "samples": 128,
    "denoise": true,
    "output_format": "png"
  }
}
```

All coordinates are in **millimetres**. Blender internally scales to metres.

`scene_file_id` must point to an existing file in the same project (kind: `feature`, `mesh`,
`step`, etc.). The geometry is passed to pyworker as base64-encoded content.

---

## Tools

### `create_render`

Create a new `.render` file with default 3-point lighting and a standard perspective camera.

```json
{
  "scene_file_id": "<uuid>",
  "name": "Hero shot",
  "resolution": [1920, 1080],
  "samples": 128,
  "parent_folder_id": "<optional-uuid>"
}
```

Response: `{ "file_id": "<uuid>", "name": "...", "path": "/.../Hero shot.render", "scene_file_id": "..." }`

---

### `set_render_camera`

Update camera position, look-at target, and field-of-view.

```json
{
  "file_id": "<uuid>",
  "position": [5000, -5000, 3000],
  "target": [0, 0, 500],
  "fov_deg": 35
}
```

Response: `{ "file_id": "...", "camera": { ... } }`

---

### `add_render_light`

Append a light to the scene.

```json
{
  "file_id": "<uuid>",
  "id": "rim",
  "kind": "sun",
  "direction": [1, -0.5, -1],
  "intensity": 2,
  "color": "#ffe8d0"
}
```

`kind` options: `sun` (directional / infinite), `area` (soft box), `point`, `spot`.

Area lights need `position` and optionally `size_mm`. Sun lights need `direction`.

---

### `set_render_material_override`

Override material for all objects (`"*"`) or a named object.

```json
{
  "file_id": "<uuid>",
  "target_pattern": "*",
  "material": {
    "kind": "principled",
    "base_color": "#b04020",
    "roughness": 0.3,
    "metallic": 0.0
  }
}
```

---

### `run_render`

Execute the render. Requires Blender installed on the worker host and pyworker running.

```json
{ "file_id": "<uuid>" }
```

Response:
```json
{
  "status": "ok",
  "file_id": "...",
  "output_b64": "<base64 PNG or EXR bytes>",
  "format": "png",
  "render_seconds": 14.7,
  "image_url": "https://..."
}
```

If Blender is not installed, the error will say `blender binary not found on PATH`.

---

## Workflow

```
create_render(scene_file_id, name)
  → set_render_camera(file_id, position, target, fov_deg)
  → add_render_light(file_id, ...)      # optional extra lights
  → set_render_material_override(file_id, "*", {...})
  → run_render(file_id)
```

`run_render` is synchronous (blocks until Cycles finishes). For heavy scenes with many
samples, this can take minutes. Reduce `samples` (16–32) for fast previews.

---

## Tips

- **Coordinates**: always millimetres. A typical part at origin means `position: [3000, -3000, 2000]` is about 3 m away.
- **Samples**: 32 = fast preview, 128 = production quality, 512+ = high-quality print.
- **Output format**: `"exr"` preserves HDR data for compositing; `"png"` for direct sharing.
- **No HDRI yet**: use `"environment": {"kind": "color", "color": "#202020"}` for dark studio or `"#e8eeff"` for daylight feel.
- **Metallic look**: `roughness: 0.05, metallic: 1.0` — pair with a bright key light.

---

## Examples

### Example 1 — Product hero shot

```json
{
  "version": 1,
  "name": "Product hero",
  "scene_file_id": "2fa8b3d1-...",
  "camera": {"position": [3500, -2500, 1800], "target": [0,0,400], "fov_deg": 40, "type": "perspective"},
  "lights": [
    {"id": "key",  "kind": "sun",  "direction": [-1,-1,-2],     "intensity": 5, "color": "#ffffff"},
    {"id": "fill", "kind": "area", "position": [3000,2000,2000], "size_mm": 800, "intensity": 2, "color": "#d0e8ff"},
    {"id": "back", "kind": "sun",  "direction": [1,0.5,-0.5],   "intensity": 1, "color": "#ffe8d0"}
  ],
  "materials_override": {"*": {"kind": "principled", "base_color": "#c8c8c8", "roughness": 0.4, "metallic": 0.0}},
  "environment": {"kind": "color", "color": "#181818"},
  "render_settings": {"resolution": [2560, 1440], "samples": 256, "denoise": true, "output_format": "png"}
}
```

---

### Example 2 — Architectural exterior with sun

```json
{
  "version": 1,
  "name": "Exterior — noon sun",
  "scene_file_id": "9b7c1a02-...",
  "camera": {"position": [15000, -20000, 8000], "target": [0,0,3000], "fov_deg": 55, "type": "perspective"},
  "lights": [
    {"id": "sun",  "kind": "sun",  "direction": [-0.5,-0.3,-1], "intensity": 8, "color": "#fff8e8"},
    {"id": "sky",  "kind": "area", "position": [0,0,30000],     "size_mm": 50000, "intensity": 1, "color": "#c8d8ff"}
  ],
  "materials_override": {"*": {"kind": "principled", "base_color": "#e0d8cc", "roughness": 0.7, "metallic": 0.0}},
  "environment": {"kind": "color", "color": "#9ab4e0"},
  "render_settings": {"resolution": [3840, 2160], "samples": 256, "denoise": true, "output_format": "png"}
}
```

---

### Example 3 — Dark studio metallic scene

```json
{
  "version": 1,
  "name": "Dark studio",
  "scene_file_id": "4d2e9f71-...",
  "camera": {"position": [2000, -2000, 1500], "target": [0,0,300], "fov_deg": 35, "type": "perspective"},
  "lights": [
    {"id": "key",  "kind": "area", "position": [1500, -500, 2000], "size_mm": 400, "intensity": 10, "color": "#ffffff"},
    {"id": "rim",  "kind": "spot", "position": [-1000, 1500, 1800], "intensity": 6, "color": "#a0c8ff"}
  ],
  "materials_override": {"*": {"kind": "principled", "base_color": "#303030", "roughness": 0.05, "metallic": 1.0}},
  "environment": {"kind": "color", "color": "#050505"},
  "render_settings": {"resolution": [1920, 1080], "samples": 512, "denoise": true, "output_format": "exr"}
}
```
