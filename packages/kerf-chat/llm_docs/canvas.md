# Project canvas: layers + display modes

Every Kerf project can have a `.canvas.json` file (kind `canvas`) pinned at
the project root. It holds project-wide layer definitions and the active
display-mode preset for the 3D viewport.

## Schema (version 1)

```jsonc
{
  "version": 1,

  // Ordered list of project layers.
  "layers": [
    {
      "id":          "L01",           // auto-assigned, e.g. L01 … L99
      "name":        "Geometry",      // display name
      "visible":     true,
      "color":       "#ffffff",       // hex color for the layer
      "linetype":    "continuous",    // "continuous" | "dashed" | "dotted"
      "material_id": null,            // optional material override UUID
      "locked":      false            // if true, geometry on this layer cannot be edited
    }
  ],

  // Display-mode presets (built-in; can be extended).
  "display_modes": [
    { "id": "shaded",    "name": "Shaded",    "wireframe": false, "edges": true,  "shadows": false, "transparency": 1.0,  "background_color": "#1a1a1a" },
    { "id": "wireframe", "name": "Wireframe", "wireframe": true,  "edges": true },
    { "id": "technical", "name": "Technical", "wireframe": false, "edges": true,  "silhouette": true, "shadows": false },
    { "id": "rendered",  "name": "Rendered",  "wireframe": false, "edges": false, "shadows": true,  "transparency": 0.95 }
  ],

  "active_display_mode": "shaded",   // must match an id in display_modes
  "active_layer":        "L01"       // must match an id in layers
}
```

Individual project files record their layer assignment in their `metadata`
JSON column under the key `layer_id`.

## Available tools

| Tool | What it does |
|------|--------------|
| `create_layer` | Add a new layer (auto-assigns id) |
| `delete_layer` | Remove a layer by id (refuses to remove the last) |
| `set_project_layer_visibility` | Show / hide a layer |
| `set_project_layer_color` | Change a layer's hex color |
| `assign_file_to_layer` | Tag a file with a layer id |
| `switch_display_mode` | Change the active viewport display mode |

All tools create `.canvas.json` at the project root automatically if it does
not yet exist.

---

## Worked example 1 — 3-layer drafting project

**Prompt:** "Set up a 3-layer drafting project: Construction lines, Main
geometry, and Annotations. Use rendered display mode."

```
create_layer(project_id=..., name="Construction lines", color="#555555")
→ { "layer_id": "L02", ... }

create_layer(project_id=..., name="Main geometry", color="#ffffff")
→ { "layer_id": "L03", ... }

create_layer(project_id=..., name="Annotations", color="#ffdd44")
→ { "layer_id": "L04", ... }

switch_display_mode(project_id=..., mode_id="rendered")
→ { "message": "active display mode set to 'rendered'" }
```

After these calls the canvas has 4 layers (L01 Geometry is always created by
default, plus the 3 new ones) and the viewport is in Rendered mode.

---

## Worked example 2 — Hide construction lines, go wireframe

**Prompt:** "Hide the construction lines layer and switch to wireframe view."

```
set_project_layer_visibility(project_id=..., layer_id="L02", visible=false)
→ { "message": "set 'L02' visible=False" }

switch_display_mode(project_id=..., mode_id="wireframe")
→ { "message": "active display mode set to 'wireframe'" }
```
