# Railings (.railing) — Parametric handrail format

A `.railing` file defines a handrail / balustrade system that follows a
polyline path. Posts and balusters are distributed evenly along the path.
Files have `kind='railing'` in the DB.

## JSON schema

```jsonc
{
  "version": 1,
  "path": [
    { "x": 0,    "y": 0, "z": 0 },
    { "x": 4480, "y": 0, "z": 2800 }
  ],
  "height_mm": 1000,              // top-rail height above tread nosing
  "top_rail": {
    "profile": "round",           // "round" | "square" | "flat"
    "size_mm": 50,                // diameter or width
    "offset_mm": 0                // lateral offset from path centre
  },
  "posts": {
    "spacing_mm": 1200,           // max centre-to-centre distance
    "profile": "round",           // "round" | "square"
    "size_mm": 40,
    "height_mm": 1000
  },
  "balusters": {
    "spacing_mm": 120,            // max gap between balusters
    "profile": "round",           // "round" | "square"
    "size_mm": 14,
    "height_mm": 900
  }
}
```

### Height limits
`height_mm` must be in **[600, 1200] mm**. Typical residential = 1000 mm,
commercial = 1100 mm.

## LLM tools

| Tool | Description |
|------|-------------|
| `create_railing` | Create railing from explicit path |
| `railing_from_stair` | Auto-generate railing along stair edge(s) |
| `set_baluster_spacing` | Update baluster spacing on existing railing |
| `validate_railing` | Check height limits and path validity |

## Examples

### 1. Stair railing — auto-generated along left and right edges

```json
{
  "tool": "railing_from_stair",
  "args": {
    "stair_file_id": "<uuid>",
    "side": "both",
    "height_mm": 1000
  }
}
```

Returns `left_file_id` and `right_file_id` for the two railing files.

### 2. Balcony railing — explicit rectangular path

```json
{
  "tool": "create_railing",
  "args": {
    "path": [
      { "x": 0,    "y": 0,    "z": 3000 },
      { "x": 6000, "y": 0,    "z": 3000 },
      { "x": 6000, "y": 3000, "z": 3000 },
      { "x": 0,    "y": 3000, "z": 3000 }
    ],
    "height_mm": 1100
  }
}
```

Flat-level balcony perimeter railing at 3 m floor height.

### 3. Ramp railing — sloped path

```json
{
  "tool": "create_railing",
  "args": {
    "path": [
      { "x": 0,    "y": 0, "z": 0   },
      { "x": 1000, "y": 0, "z": 100 },
      { "x": 2000, "y": 0, "z": 200 },
      { "x": 3000, "y": 0, "z": 300 },
      { "x": 4000, "y": 0, "z": 400 },
      { "x": 5000, "y": 0, "z": 500 }
    ],
    "height_mm": 1000
  }
}
```

Ramp at 1:10 gradient; posts and balusters distribute automatically
along the sloped path.
