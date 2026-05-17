# kerf-mates · tools.py

LLM tool registration for assembly mates and tolerance analysis.

## Registered tools

| Tool | Write | Description |
|---|---|---|
| `add_mate` | yes | Add a mate constraint to an assembly |
| `delete_mate` | yes | Remove a mate constraint by id |
| `list_mates` | no | List all mates in an assembly |
| `solve_assembly` | no | Run the geometric constraint solver |
| `tolerance_auto_chain` | no | BFS chain-walk + worst-case/RSS analysis |

## `add_mate`

Appends a mate constraint to an assembly document. Calls `validate_mate()`
before writing.

```json
{
  "assembly_file_id": "uuid",
  "type": "coincident",
  "refs": [
    {"component_id": "comp_A", "feature_name": "face_top", "feature_type": "face"},
    {"component_id": "comp_B", "feature_name": "face_bottom", "feature_type": "face"}
  ]
}
```

For distance/angle mates, `value` and `unit` are required:

```json
{
  "assembly_file_id": "uuid",
  "type": "distance",
  "refs": [
    {"component_id": "comp_A", "feature_name": "face_left", "feature_type": "face"},
    {"component_id": "comp_B", "feature_name": "face_right", "feature_type": "face"}
  ],
  "value": 10.0,
  "unit": "mm"
}
```

## `delete_mate`

```json
{"assembly_file_id": "uuid", "mate_id": "mate_001"}
```

## `list_mates`

```json
{"assembly_file_id": "uuid"}
```

Returns: `{mates: [...], count: N}`.

## `solve_assembly`

```json
{"assembly_file_id": "uuid"}
```

Returns: `{converged, iterations, residual, transform_count, warnings}`.

## `tolerance_auto_chain`

```json
{
  "assembly_file_id": "uuid",
  "start_ref": "comp_A::face_left",
  "end_ref": "comp_B::face_right"
}
```

Returns: `{chain_length, contributions, worst_case, rss, warnings}`.

## Validation rules (`validate_mate`)

- `type` must be one of: `coincident`, `concentric`, `parallel`,
  `perpendicular`, `distance`, `angle`, `tangent`.
- Both refs must be present; each must have `feature_type` in
  `{face, edge, vertex, axis}`.
- `distance` and `angle` types require numeric `value` and non-empty `unit`.
- `feature_name` is preferred over the legacy `feature_id` field.

## Error codes

| Code | Meaning |
|---|---|
| `BAD_ARGS` | Validation failure |
| `NOT_FOUND` | Assembly file or mate id not found |
| `SOLVE_ERROR` | Solver did not converge |
