# kerf-imports · tools/feature_mirror.py

LLM tool: append a `mirror_feature` node to a `.feature` file.

## LLM tool: `feature_mirror`

Mirrors an existing feature or body about a world coordinate plane or a
planar face. Exactly one source and one mirror reference must be supplied.

```json
{
  "file_id": "uuid",
  "source_feature_id": "extrude_001",
  "mirror_plane": "XZ",
  "merge": true,
  "name": "mirror_left_wall"
}
```

### Parameters

| Parameter | Type | Required | Mutual exclusion |
|---|---|---|---|
| `file_id` | string (UUID) | yes | — |
| `source_feature_id` | string | one-of | mutually exclusive with `source_body_id` |
| `source_body_id` | string | one-of | mutually exclusive with `source_feature_id` |
| `mirror_plane` | `"XY"`, `"XZ"`, or `"YZ"` | one-of | mutually exclusive with `mirror_face_id` |
| `mirror_face_id` | integer | one-of | post-evaluation face index |
| `merge` | boolean | no | default `true` — boolean-union mirrored copy with original |
| `name` | string | no | human-readable label for the node |

### Returns

```json
{
  "file_id": "uuid",
  "id": "mirror_feature_001",
  "op": "mirror_feature"
}
```

## Validation

`validate_mirror_args()` checks:
- Exactly one of `source_feature_id` / `source_body_id` provided.
- Exactly one of `mirror_plane` / `mirror_face_id` provided.
- `mirror_plane` must be `"XY"`, `"XZ"`, or `"YZ"` (case-insensitive input,
  normalized to uppercase).

## Node shape

```json
{
  "id": "mirror_feature_001",
  "op": "mirror_feature",
  "params": {
    "source_feature_id": "extrude_001",
    "mirror_plane": "XZ",
    "merge": true
  }
}
```

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Validation failure (mutual exclusion, invalid plane) |
| `NOT_FOUND` | Feature file not found |
| `ERROR` | `append_feature_node` internal error |
