# kerf-imports · tools/feature_draft.py

LLM tool: append a `draft` feature node to a `.feature` file.

## LLM tool: `feature_draft`

Appends a draft operation to a parametric feature file. Draft angles a
face or set of faces relative to the pull direction.

```json
{
  "file_id": "uuid",
  "face_ids": [12, 13],
  "angle_deg": 2.0,
  "pull_direction": "outward",
  "name": "draft_A"
}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_id` | string (UUID) | yes | Target `.feature` file |
| `face_ids` | array[int] | yes | Post-evaluation face indices to draft |
| `angle_deg` | number | yes | Draft angle; range **[-30, 30]** degrees |
| `pull_direction` | string | yes | `"inward"` or `"outward"` |
| `name` | string | no | Optional human-readable label |

### Returns

```json
{
  "file_id": "uuid",
  "id": "draft_001",
  "op": "draft"
}
```

## Implementation

Calls `append_feature_node(ctx, fid, node)` from `kerf_cad_core.surfacing`.
The node shape:

```json
{
  "id": "draft_001",
  "op": "draft",
  "name": "draft_A",
  "params": {
    "face_ids": [12, 13],
    "angle_deg": 2.0,
    "pull_direction": "outward"
  }
}
```

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | `angle_deg` outside ±30°, invalid `pull_direction`, no `file_id` |
| `NOT_FOUND` | Feature file not found |
