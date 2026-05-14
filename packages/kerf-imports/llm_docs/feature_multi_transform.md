# `feature_multi_transform` — compose multiple pattern operations on an existing feature

Appends a `multi_transform` node to a `.feature` file. This is the FreeCAD-style
Multi-Transform feature that composes multiple pattern operations (linear,
polar, mirror) in sequence on a single source feature. The result is the
cartesian product of all transform instances (e.g., linear 4x combined with
polar 3x produces 12 instances).

## Schema

```json
{
  "id": "multi_transform-1",
  "op": "multi_transform",
  "params": {
    "source_feature_id": "pad-1",
    "transforms": [
      { "kind": "linear", "direction": "x", "count": 4, "spacing": 10 },
      { "kind": "polar",  "axis": "z", "count": 3, "total_angle_deg": 360 }
    ]
  },
  "name": "bolt_circle_pattern"
}
```

### Parameters

| Parameter           | Type           | Required | Default | Notes                                            |
|---------------------|----------------|----------|---------|--------------------------------------------------|
| `file_id`           | string (uuid)  | yes      | —       | Target `.feature` file id                        |
| `source_feature_id` | string         | yes      | —       | Id of the source feature to transform             |
| `transforms`        | array         | yes      | —       | Array of 1-4 transform operations                 |
| `name`              | string         | no       | `""`    | Human-readable label for the node                 |

#### Transform Object Properties

**Linear Transform:**
| Property   | Type   | Required | Notes                     |
|------------|--------|----------|---------------------------|
| `kind`     | string | yes      | Must be `"linear"`        |
| `direction` | string | yes      | `"x"`, `"y"`, or `"z"`    |
| `count`    | integer| yes      | >= 2                      |
| `spacing`  | number | yes      | > 0 (mm)                  |

**Polar Transform:**
| Property        | Type   | Required | Notes                     |
|-----------------|--------|----------|---------------------------|
| `kind`          | string | yes      | Must be `"polar"`         |
| `axis`          | string | yes      | `"x"`, `"y"`, or `"z"`    |
| `count`         | integer| yes      | >= 2                      |
| `total_angle_deg` | number | yes   | 0 < angle <= 360          |

**Mirror Transform:**
| Property       | Type   | Required | Notes                              |
|----------------|--------|----------|------------------------------------|
| `kind`         | string | yes      | Must be `"mirror"`                 |
| `plane_or_face`| string | yes      | `"XY"`, `"XZ"`, `"YZ"`, or face id |

## Examples

### Bolt circle of bolt circles

Create 3 evenly-spaced copies of a 4x linear pattern of bolt holes, producing
a 12-instance radial array (4 bolts x 3 copies):

```text
feature_multi_transform(
  file_id            = <bracket.feature id>,
  source_feature_id  = "pad-1",
  transforms         = [
    { kind: 'linear',  direction: 'x',     count: 4, spacing: 8  },
    { kind: 'polar',   axis: 'z',          count: 3, total_angle_deg: 360 }
  ],
  name               = "bolt_circle_of_holes"
)
```

Resulting node:

```json
{
  "id": "multi_transform-1",
  "op": "multi_transform",
  "name": "bolt_circle_of_holes",
  "params": {
    "source_feature_id": "pad-1",
    "transforms": [
      { "kind": "linear", "direction": "x", "count": 4, "spacing": 8 },
      { "kind": "polar",  "axis": "z", "count": 3, "total_angle_deg": 360 }
    ]
  }
}
```

### Mirror-then-linear-pattern of a slot

Mirror a slot feature across the XY plane, then pattern the result in a
2x4 linear array:

```text
feature_multi_transform(
  file_id            = <plate.feature id>,
  source_feature_id  = "pocket-1",
  transforms         = [
    { kind: 'mirror', plane_or_face: 'XY' },
    { kind: 'linear', direction: 'x',     count: 4, spacing: 15 },
    { kind: 'linear', direction: 'y',     count: 2, spacing: 15 }
  ],
  name               = "mirrored_slot_array"
)
```

Resulting node:

```json
{
  "id": "multi_transform-1",
  "op": "multi_transform",
  "name": "mirrored_slot_array",
  "params": {
    "source_feature_id": "pocket-1",
    "transforms": [
      { "kind": "mirror", "plane_or_face": "XY" },
      { "kind": "linear", "direction": "x", "count": 4, "spacing": 15 },
      { "kind": "linear", "direction": "y", "count": 2, "spacing": 15 }
    ]
  }
}
```

This produces 16 instances (2 mirror x 4 x 2).

## Validation rules

- `transforms` must be a non-empty array of 1-4 transform objects.
- `source_feature_id` must reference an existing feature node in the feature tree.
- Each transform object must have the required properties for its `kind`:
  - `linear`: requires `direction`, `count` (>= 2), and `spacing` (> 0).
  - `polar`: requires `axis`, `count` (>= 2), and `total_angle_deg` (0 < angle <= 360).
  - `mirror`: requires `plane_or_face`.
- `direction` and `axis` are case-insensitive.
- `file_id` must be a valid UUID pointing to a `feature`-kind file.