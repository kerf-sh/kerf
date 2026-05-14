# `helix` feature node

A helix sweeps a closed cross-section profile along a parametric 3-D coil
path. The resulting solid is the swept body (spring coil, thread blank,
auger flight, worm gear, etc.).

Use the `feature_helix` tool to append a `helix` node to any `.feature`
file, or write the JSON directly.

## Node shape

```json
{
  "id": "helix-1",
  "op": "helix",
  "pitch_mm": 2.5,
  "height_mm": 20.0,
  "radius_mm": 8.0,
  "direction": "right",
  "cone_half_angle_deg": 0,
  "origin": [0, 0, 0],
  "axis": [0, 0, 1],
  "profile_sketch_id": "<uuid>"
}
```

### Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pitch_mm` | number | required | Axial distance per full turn (mm). Must be > 0. |
| `height_mm` | number | required | Total axial height (mm). Must be > 0. |
| `radius_mm` | number | required | Base coil radius (mm). Must be > 0. |
| `direction` | `"right"` \| `"left"` | `"right"` | `"right"` = CCW from above (standard M-thread). `"left"` = CW (left-hand thread). |
| `cone_half_angle_deg` | number | `0` | Half-angle of taper. `0` = cylindrical. Must be `[0, 90)`. |
| `origin` | `[x, y, z]` | `[0, 0, 0]` | Base point of the helix. |
| `axis` | `[x, y, z]` | `[0, 0, 1]` | Axis direction vector (need not be unit). |
| `profile_sketch_id` | UUID string | omit | Closed-profile sketch to sweep. Omit for a default 0.5 mm circle (preview only). |
| `name` | string | omit | Human-readable label. |
| `id` | string | auto | Node id. Auto-generated as `helix-N` if omitted. |

**Derived values** (not stored, returned by the tool):

- `turns = height_mm / pitch_mm`

## Tool usage

```python
feature_helix(
    file_id            = "<feature file uuid>",
    pitch_mm           = 2.5,
    height_mm          = 20.0,
    radius_mm          = 8.0,
    direction          = "right",
    cone_half_angle_deg= 0,
    profile_sketch_id  = "<profile sketch uuid>",   # optional
)
```

Returns `{ "file_id", "id", "op": "helix", "turns" }`.

---

## Worked examples

### 1. Compression spring

A steel compression spring: 10 turns, 20 mm coil diameter, 3 mm wire.

```python
# 1. Create a tiny circle sketch for the wire cross-section (3 mm radius)
create_sketch(path="/spring/wire.sketch")
# add circle entity at origin, radius 1.5

feature_helix(
    file_id  = spring_feature_id,
    pitch_mm = 4.0,          # 3 mm wire + 1 mm gap
    height_mm= 40.0,         # 10 turns × 4 mm pitch
    radius_mm= 10.0,         # 20 mm coil diameter → 10 mm radius
    direction= "right",
    profile_sketch_id = wire_sketch_id,
)
```

The OCCT worker sweeps the 3 mm circle along the helix path using
`BRepOffsetAPI_MakePipeShell`, yielding a solid coil body.

---

### 2. M6 thread blank

Rough-cut thread blank for an M6 bolt: pitch 1 mm, nominal diameter 6 mm,
20 mm of thread.

```python
# Profile: annular ring 2.7–3 mm radius (outer thread depth 0.3 mm)
feature_helix(
    file_id  = bolt_feature_id,
    pitch_mm = 1.0,
    height_mm= 20.0,
    radius_mm= 3.0,          # 6 mm nominal → 3 mm radius
    direction= "right",
    profile_sketch_id = thread_profile_sketch_id,
)
```

For a left-hand thread (e.g. a left pedal spindle) set `direction="left"`.

---

### 3. Conical auger flight

Single-flight auger that widens from a 30 mm root to a 90 mm tip over
400 mm of height, pitch 50 mm (8 turns).

```python
# half-angle: atan((90-30)/2 / 400) ≈ 4.3°
import math
cone_angle = math.degrees(math.atan((45 - 15) / 400))   # ≈ 4.29°

feature_helix(
    file_id             = auger_feature_id,
    pitch_mm            = 50.0,
    height_mm           = 400.0,
    radius_mm           = 15.0,       # start radius (root)
    cone_half_angle_deg = cone_angle,
    direction           = "right",
    profile_sketch_id   = flight_profile_id,
)
```

The radius at the tip = `15 + 400 × tan(4.29°) ≈ 45 mm` (90 mm diameter).
