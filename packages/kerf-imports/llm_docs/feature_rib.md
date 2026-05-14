# `feature_rib` — parametric reinforcement wall

Appends a `rib` node to a `.feature` file. Rib creates a parametric
reinforcement wall by offsetting a closed sketch profile and sweeping it
into a solid wall. The OCCT worker receives an offset polyline and sweeps
it using `BRepOffsetAPI_MakePipeShell`.

## Schema

```json
{
  "id": "rib-1",
  "op": "rib",
  "params": {
    "sketch_id": "<uuid>",
    "thickness_mm": 3.0,
    "both_sides": false,
    "midplane": false,
    "draft_angle_deg": 0
  }
}
```

### Parameters

| Parameter          | Type        | Required | Default | Notes                                              |
|--------------------|-------------|----------|---------|----------------------------------------------------|
| `file_id`          | string (uuid) | yes    | —       | Target `.feature` file id                          |
| `sketch_id`        | string      | yes      | —       | Closed-profile sketch id to rib                    |
| `thickness_mm`     | number      | yes      | —       | Wall thickness in mm; must be > 0                  |
| `both_sides`       | boolean     | no       | `false` | Extrude symmetrically about the sketch plane       |
| `midplane`         | boolean     | no       | `false` | Center extrusion on the sketch plane               |
| `draft_angle_deg`  | number      | no       | `0`     | Draft taper angle for mold release, degrees        |
| `name`             | string      | no       | `""`    | Human-readable label for the node                   |

**Offset logic**: When `both_sides=false` and `midplane=false`, the
profile is offset outward by `thickness_mm`. When `both_sides=true` the
sketch is offset by `thickness_mm/2` in both directions. When
`midplane=true` no offset is applied (the sweep is centered).

## Examples

### Housing internal stiffener

A 3 mm nylon housing body needs an internal vertical stiffener rib:

```python
feature_rib(
    file_id        = housing_feature_id,
    sketch_id      = stiffener_sketch_id,
    thickness_mm   = 3.0,
    both_sides     = False,
    midplane       = False,
    draft_angle_deg= 0,
    name           = "wall_stiffener"
)
```

Resulting node:

```json
{
  "id": "rib-1",
  "op": "rib",
  "name": "wall_stiffener",
  "params": {
    "sketch_id": "<stiffener sketch uuid>",
    "thickness_mm": 3.0,
    "both_sides": false,
    "midplane": false,
    "draft_angle_deg": 0
  }
}
```

---

### Gusset on L-bracket

A steel L-bracket benefits from a 2 mm gusset filling the corner, with
1° draft for mold release and symmetric extrusion:

```python
feature_rib(
    file_id        = bracket_feature_id,
    sketch_id      = gusset_sketch_id,
    thickness_mm   = 2.0,
    both_sides     = True,
    midplane       = False,
    draft_angle_deg= 1.0,
    name           = "corner_gusset"
)
```

```json
{
  "id": "rib-2",
  "op": "rib",
  "name": "corner_gusset",
  "params": {
    "sketch_id": "<gusset sketch uuid>",
    "thickness_mm": 2.0,
    "both_sides": true,
    "midplane": false,
    "draft_angle_deg": 1.0
  }
}
```

## Validation rules

- `file_id` must be a valid UUID pointing to a `feature`-kind file.
- `sketch_id` must be a non-empty string.
- `thickness_mm` must be a positive number (> 0).
- `both_sides` and `midplane` are booleans (default false).
- `draft_angle_deg` must be a number (default 0).