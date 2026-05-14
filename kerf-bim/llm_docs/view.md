# View (.view.json) — Saved BIM views

A **view** is a named, saved slice of a BIM model. It stores the camera / cut
configuration, element filters, display overrides, and attached annotations.
Views live as files with `kind = 'view'` in the project tree.

---

## Schema

```jsonc
{
  "version": 1,
  "id": "uuid",
  "name": "Level 1 Floor Plan",
  "kind": "plan",              // plan | section | elevation | 3d
  "bim_file_id": "bim-uuid",  // UUID of the linked .bim file
  "level_id": "L01",           // for plan kind — which level to display
  "cut_plane_z_mm": 1200,      // plan cut height in mm above level origin
  "section_origin": [0, 0, 0], // for section / elevation
  "section_direction": [1, 0, 0],
  "crop_box": {                // null = no crop
    "min": [0, 0, 0],
    "max": [10000, 8000, 3000]
  },
  "filters": [
    {"expr": "category=='wall' AND fire_rating>='2hr'"}
  ],
  "display_overrides": {
    "by_category": {
      "wall": {"color": "#888"},
      "door": {"hatch": "wood"}
    }
  },
  "annotations": [
    {"id": "tag1", "kind": "door_tag",   "element_id": "door-1", "position": [2000, 1000, 0]},
    {"id": "dim1", "kind": "linear_dim", "from": [0,0,0],        "to": [5000,0,0], "offset": 500}
  ]
}
```

### Kinds

| kind      | Required fields                         |
|-----------|-----------------------------------------|
| plan      | bim_file_id, level_id, cut_plane_z_mm   |
| section   | bim_file_id, section_origin, section_direction |
| elevation | bim_file_id, section_origin, section_direction |
| 3d        | bim_file_id                             |

### Filter expressions

Filters use a simple expression language:

- `field=='value'` — equality (string)
- `field>value` / `field>=value` / `field<value` / `field<=value` — comparison
- `expr AND expr` — both must be true
- `expr OR expr`  — either must be true

---

## Tools

| Tool | Description |
|------|-------------|
| `create_view` | Create a new `.view.json` file |
| `set_view_filters` | Replace the filter list |
| `add_view_annotation` | Attach a tag, dimension, or leader |
| `run_view` | Resolve filters and return visible elements |

---

## Examples

### 1 — Create a floor-plan view for Level 1

```json
{
  "tool": "create_view",
  "args": {
    "path": "/Office Tower/Views/L01_FloorPlan.view.json",
    "name": "Level 1 Floor Plan",
    "kind": "plan",
    "bim_file_id": "bim-file-uuid",
    "level_id": "L01",
    "cut_plane_z_mm": 1200
  }
}
```

### 2 — Filter to show only fire-rated walls

```json
{
  "tool": "set_view_filters",
  "args": {
    "file_id": "view-file-uuid",
    "filters": [
      {"expr": "category=='wall' AND fire_rating>='2hr'"}
    ]
  }
}
```

### 3 — Run the view to get visible elements

```json
{
  "tool": "run_view",
  "args": {
    "file_id": "view-file-uuid"
  }
}
// Returns: { "visible_count": 12, "elements": [...] }
```
