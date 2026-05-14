# Curtain Wall — LLM Reference

## File format: `.curtain_wall`

```json
{
  "version": 1,
  "name": "Curtain Wall",
  "base_curve_or_wall_id": "curve-abc-123",
  "height_mm": 3000,
  "u_divisions": [
    { "type": "count", "value": 4 }
  ],
  "v_divisions": [
    { "type": "count", "value": 6 }
  ],
  "panel_type": {
    "kind": "glass",
    "material_id": null,
    "color": null
  },
  "mullion_type": {
    "profile": "square",
    "size_mm": 50,
    "color": null
  },
  "top_rail": {
    "profile": "square",
    "size_mm": 50,
    "visible": true
  },
  "bottom_rail": {
    "profile": "square",
    "size_mm": 50,
    "visible": true
  }
}
```

- `base_curve_or_wall_id` — ID of the base sketch curve or wall to attach the curtain wall to.
- `height_mm` — total height of the curtain wall in mm.
- `u_divisions` — array of division specs along the base curve direction (u in [0, 1]).
- `v_divisions` — array of division specs along the height direction (v in [0, 1]).
- `panel_type.kind` — one of `glass`, `solid`, `opening`.
- `mullion_type.profile` — `square` or `round`.

### Division Types

| Type | Value | Description |
|------|-------|-------------|
| `count` | positive integer | Creates N+1 grid lines evenly spaced |
| `spacing` | positive number (mm) | Creates ceil(length/spacing)+1 grid lines |
| `mixed` | array of sub-specs | Alternates between sub-divisions |

---

## Example 1: Glass Facade 4x6 Grid

```json
{
  "version": 1,
  "name": "South Facade",
  "base_curve_or_wall_id": "sketch-curve-001",
  "height_mm": 4000,
  "u_divisions": [
    { "type": "count", "value": 6 }
  ],
  "v_divisions": [
    { "type": "count", "value": 8 }
  ],
  "panel_type": {
    "kind": "glass",
    "material_id": "mat-glass-clear",
    "color": null
  },
  "mullion_type": {
    "profile": "square",
    "size_mm": 50,
    "color": "#888888"
  },
  "top_rail": {
    "profile": "square",
    "size_mm": 75,
    "visible": true
  },
  "bottom_rail": {
    "profile": "square",
    "size_mm": 75,
    "visible": true
  }
}
```

---

## Example 2: Mixed Panel Storefront

```json
{
  "version": 1,
  "name": "Storefront",
  "base_curve_or_wall_id": "sketch-curve-002",
  "height_mm": 3000,
  "u_divisions": [
    { "type": "mixed", "value": [
      { "type": "count", "value": 2 },
      { "type": "spacing", "value": 800 },
      { "type": "count", "value": 2 }
    ]}
  ],
  "v_divisions": [
    { "type": "count", "value": 1 },
    { "type": "spacing", "value": 600 }
  ],
  "panel_type": {
    "kind": "solid",
    "material_id": "mat-aluminum-panel",
    "color": "#C0C0C0"
  },
  "mullion_type": {
    "profile": "round",
    "size_mm": 40,
    "color": "#333333"
  },
  "top_rail": {
    "profile": "square",
    "size_mm": 50,
    "visible": false
  },
  "bottom_rail": {
    "profile": "square",
    "size_mm": 100,
    "visible": true
  }
}
```

---

## Available Tools

### `create_curtain_wall`

Create a new `.curtain_wall` file attached to a base curve or wall.

```json
{
  "file_id": "optional-uuid",
  "base_curve_or_wall_id": "curve-abc-123",
  "height_mm": 3000,
  "u_divisions": [{ "type": "count", "value": 4 }],
  "v_divisions": [{ "type": "count", "value": 6 }],
  "panel_kind": "glass"
}
```

### `set_curtain_wall_division`

Update u or v division scheme on an existing curtain wall.

```json
{
  "file_id": "uuid-of-curtain-wall",
  "axis": "u",
  "divisions": [{ "type": "spacing", "value": 500 }]
}
```

### `set_curtain_wall_panel_type`

Update panel type on an existing curtain wall.

```json
{
  "file_id": "uuid-of-curtain-wall",
  "panel_type": {
    "kind": "opening",
    "material_id": "mat-001",
    "color": "#FF0000"
  }
}
```

### `set_curtain_wall_mullion_type`

Update mullion type on an existing curtain wall.

```json
{
  "file_id": "uuid-of-curtain-wall",
  "mullion_type": {
    "profile": "round",
    "size_mm": 75,
    "color": "#000000"
  }
}
```

### `validate_curtain_wall`

Validate a curtain wall file for schema correctness.

```json
{
  "file_id": "uuid-of-curtain-wall"
}
```
