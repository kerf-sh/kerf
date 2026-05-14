# Stairs (.stair) — Parametric staircase format

A `.stair` file encodes a multi-flight parametric staircase. Geometry is
derived from the params plus each flight's start point and direction.
Files have `kind='stair'` in the DB.

## JSON schema

```jsonc
{
  "version": 1,
  "total_rise_mm": 2800,          // total vertical rise
  "total_run_mm": 3360,           // total horizontal run
  "tread_depth_mm": 280,          // going / tread depth
  "riser_height_mm": 175,         // vertical riser height
  "nosing_mm": 25,                // horizontal nosing overhang
  "width_mm": 1000,               // stair clear width
  "flights": [
    {
      "id": "flight-1",
      "start_point": [0, 0, 0],   // [x, y, z] mm — bottom of flight
      "direction": [1, 0, 0],     // unit direction vector (horizontal)
      "step_count": 16            // number of risers
    }
  ],
  "landings": [
    {
      "id": "landing-1",
      "position": [2800, 0, 1400], // corner [x, y, z] mm
      "size_mm": [1200, 1000]      // [width, depth]
    }
  ],
  "handedness": "right"           // "right" | "left" — railing side
}
```

### Comfort formula
`2 × riser_height_mm + tread_depth_mm` must be in **[550, 700] mm**.
- riser_height_mm: 100 – 220 mm
- tread_depth_mm: 200 – 350 mm

## LLM tools

| Tool | Description |
|------|-------------|
| `create_stair` | Create a stair file (straight / L / U) |
| `add_stair_flight` | Append a flight to an existing stair |
| `add_stair_landing` | Append a landing platform |
| `validate_stair` | Check code compliance (2R+T formula) |

## Examples

### 1. Straight stair — 2.8 m rise

```json
{
  "tool": "create_stair",
  "args": {
    "total_rise_mm": 2800,
    "total_run_mm": 4480,
    "kind": "straight",
    "start_point": [0, 0, 0],
    "direction": [1, 0, 0],
    "riser_height_mm": 175,
    "tread_depth_mm": 280,
    "width_mm": 1200
  }
}
```

16 steps, 2R+T = 630 (comfort code pass).

### 2. L-shaped stair — 90° turn at mid-landing

```json
{
  "tool": "create_stair",
  "args": {
    "total_rise_mm": 2800,
    "total_run_mm": 4480,
    "kind": "L",
    "start_point": [0, 0, 0],
    "riser_height_mm": 175,
    "tread_depth_mm": 280,
    "width_mm": 1000
  }
}
```

Two 8-step flights at 90°, one intermediate landing. First leg runs +x,
second leg runs +y.

### 3. U-shaped stair — 180° switchback

```json
{
  "tool": "create_stair",
  "args": {
    "total_rise_mm": 2800,
    "total_run_mm": 4480,
    "kind": "U",
    "start_point": [0, 0, 0],
    "riser_height_mm": 175,
    "tread_depth_mm": 280,
    "width_mm": 1000
  }
}
```

Two 8-step flights in opposite directions (first +x, second −x),
offset by `width_mm` in y. One mid-landing.
