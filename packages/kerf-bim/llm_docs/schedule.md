# Schedule (.schedule.json) — Revit-style query DSL

A `.schedule.json` file defines a parameterized query over a `.bim` file's elements.
It supports filtering, sorting, grouping, and column projection — similar to Revit
schedule views or a simple SQL SELECT.

## JSON shape

```json
{
  "version": 1,
  "name": "Concrete Walls",
  "target_category": "Wall",
  "filters": [
    { "field": "material", "op": "eq", "value": "Concrete" }
  ],
  "columns": [
    { "field": "name", "label": "Mark" },
    { "field": "height", "label": "Height (mm)", "format": "integer" },
    { "field": "thickness", "label": "Thickness (mm)" }
  ],
  "group_by": "material",
  "sort_by": "name"
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | integer | Must be `1` |
| `name` | string | Schedule display name |
| `target_category` | string | One of: `Wall`, `Door`, `Window`, `Room`, `Slab`, `Space`, `Opening`, `Level`, `Site` |
| `filters` | array | List of filter objects |
| `columns` | array | List of column projection objects |
| `group_by` | string? | Optional field to group results by |
| `sort_by` | string? | Optional field to sort by (`field` or `field:asc` / `field:desc`) |

### Filter operators

| Op | Meaning |
|----|---------|
| `eq` | equals |
| `ne` | not equals |
| `gt` | greater than |
| `lt` | less than |
| `gte` | greater than or equal |
| `lte` | less than or equal |
| `in` | value is in array |
| `contains` | string/array contains value |

### Nested fields

Use dot-notation for nested access: `geometry.area`, `site.latitude`.

## Example 1 — Door Schedule

```json
{
  "version": 1,
  "name": "Door Schedule",
  "target_category": "Door",
  "filters": [],
  "columns": [
    { "field": "name", "label": "Mark" },
    { "field": "width", "label": "Width (mm)" },
    { "field": "height", "label": "Height (mm)" }
  ],
  "sort_by": "name"
}
```

**Bim source:**
```json
{
  "elements": [
    { "type": "Door", "name": "D1", "width": 900, "height": 2100 },
    { "type": "Door", "name": "D2", "width": 800, "height": 2100 },
    { "type": "Door", "name": "D3", "width": 1000, "height": 2400 }
  ]
}
```

**Result:**
```json
{
  "columns": [
    { "field": "name", "label": "Mark", "format": null },
    { "field": "width", "label": "Width (mm)", "format": null },
    { "field": "height", "label": "Height (mm)", "format": null }
  ],
  "rows": [
    [{ "name": "D1", "width": 900, "height": 2100 }],
    [{ "name": "D2", "width": 800, "height": 2100 }],
    [{ "name": "D3", "width": 1000, "height": 2400 }]
  ]
}
```

## Example 2 — Room Area Schedule

```json
{
  "version": 1,
  "name": "Room Area Schedule",
  "target_category": "Room",
  "filters": [],
  "columns": [
    { "field": "name", "label": "Room Name" },
    { "field": "level", "label": "Level" },
    { "field": "area", "label": "Area (m²)", "format": "decimal" }
  ],
  "sort_by": "name"
}
```

**Bim source:**
```json
{
  "elements": [
    { "type": "Room", "name": "Living Room", "level": "L1", "area": 45.5 },
    { "type": "Room", "name": "Bedroom 1", "level": "L2", "area": 22.0 },
    { "type": "Room", "name": "Kitchen", "level": "L1", "area": 18.0 }
  ]
}
```

**Result:**
```json
{
  "columns": [
    { "field": "name", "label": "Room Name", "format": null },
    { "field": "level", "label": "Level", "format": null },
    { "field": "area", "label": "Area (m²)", "format": "decimal" }
  ],
  "rows": [
    [{ "name": "Bedroom 1", "level": "L2", "area": 22.0 }],
    [{ "name": "Kitchen", "level": "L1", "area": 18.0 }],
    [{ "name": "Living Room", "level": "L1", "area": 45.5 }]
  ]
}
```

## LLM tools

| Tool | Description |
|------|-------------|
| `create_schedule` | Create a new `.schedule.json` file in the project tree |
| `update_schedule_filter` | Update the filter on an existing `.schedule.json` file |
| `run_schedule` | Execute a `.schedule.json` against a `.bim` file; returns the table JSON |