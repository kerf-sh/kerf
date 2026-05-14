# `feature_boolean` — CSG boolean between two solid bodies

Appends a `boolean` node to a `.feature` file. Performs a constructive solid
geometry (CSG) operation between two existing feature bodies: `cut` (A − B),
`fuse` (A ∪ B), or `common` (A ∩ B).

**Both operands must be solids.** If either is a surface body (e.g. from
`sweep1` open-profile, `blend_srf`, `network_srf`), call `feature_to_solid` on
it first to promote it to a `TopoDS_Solid`. The worker will error with a clear
message pointing at `feature_to_solid` if you pass a non-solid.

See the [NURBS booleans v1 design](../../docs/plans/nurbs-booleans-v1.md) for
the full rationale, fallback paths, and the `BRepAlgoAPI_Common_3` identity
fallback (`A ∩ B = A − (A − B)`) used when the Common binding is absent.

## Schema

```json
{
  "id": "boolean-1",
  "op": "boolean",
  "target_a_id": "pad-1",
  "target_b_id": "sweep1-3",
  "kind": "cut"
}
```

### Parameters

| Parameter      | Type          | Required | Default | Notes                                                          |
|----------------|---------------|----------|---------|----------------------------------------------------------------|
| `file_id`      | string (uuid) | yes      | —       | Target `.feature` file id                                      |
| `target_a_id`  | string        | yes      | —       | First operand — preserved body on cut, first union body on fuse |
| `target_b_id`  | string        | yes      | —       | Second operand — tool body on cut                              |
| `kind`         | string (enum) | yes      | —       | `"cut"`, `"fuse"`, or `"common"`                               |
| `options.id`   | string        | no       | auto    | Explicit node id (`"boolean-N"`)                               |

### `kind` values

| Value      | Operation | Notes                                               |
|------------|-----------|-----------------------------------------------------|
| `"cut"`    | A − B     | Subtracts B from A                                  |
| `"fuse"`   | A ∪ B     | Union of A and B into one solid                     |
| `"common"` | A ∩ B     | Intersection — only the overlapping volume is kept  |

## Worked examples

### 1. Subtract a swept hole from a pad (cut)

```json
[
  { "id": "pad-1",     "op": "pad",     "sketch_path": "/base.sketch", "height": 20 },
  { "id": "sweep1-1",  "op": "sweep1",  "profile_sketch_path": "/circle_5mm.sketch", "path_sketch_path": "/curved_path.sketch" },
  { "id": "boolean-1", "op": "boolean", "target_a_id": "pad-1", "target_b_id": "sweep1-1", "kind": "cut" }
]
```

### 2. Fuse two pads into one body

```json
[
  { "id": "pad-1",     "op": "pad",     "sketch_path": "/body.sketch",  "height": 20 },
  { "id": "pad-2",     "op": "pad",     "sketch_path": "/flange.sketch", "height": 5  },
  { "id": "boolean-1", "op": "boolean", "target_a_id": "pad-1", "target_b_id": "pad-2", "kind": "fuse" }
]
```

### 3. Promote a blend surface to solid then boolean-fuse

```json
[
  { "id": "pad-1",       "op": "pad",        "sketch_path": "/box_a.sketch", "height": 30 },
  { "id": "blend_srf-1", "op": "blend_srf",  "target_id": "pad-1", "edge1_id": 1, "edge2_id": 4 },
  { "id": "to_solid-1",  "op": "to_solid",   "target_id": "blend_srf-1" },
  { "id": "boolean-1",   "op": "boolean",    "target_a_id": "pad-1", "target_b_id": "to_solid-1", "kind": "fuse" }
]
```

## Error messages

| Message | Cause |
|---|---|
| `boolean: target_a 'X' not found in evaluated tree` | `target_a_id` refers to a node that hasn't been evaluated yet (wrong order) |
| `boolean: target_a is a SHELL, not a solid — run feature_to_solid on 'X' first` | Operand is still a surface body; add a `to_solid` node before the boolean |
| `boolean: cut algorithm failed (BOPAlgo error)` | OCCT's boolean algorithm failed; try adjusting operand tolerances |
| `boolean: common produced an empty result (operands may not intersect)` | The two bodies do not overlap; check their positions |
| `boolean: unknown kind 'foo'` | `kind` must be `"cut"`, `"fuse"`, or `"common"` |
