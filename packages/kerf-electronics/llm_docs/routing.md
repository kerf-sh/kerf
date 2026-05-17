# kerf-electronics · routing.py

Manual PCB trace routing tools. Accept and return `circuit_json` dicts.
No database I/O — the caller writes the result back via `write_file`/`edit_file`.

Coexists with `autoroute_circuit` (see `autoroute.md`). Manual and auto
routing are complementary.

## LLM tools

### `route_trace_segments`

Add one or more manually-routed trace segments to a CircuitJSON board.

```json
{
  "circuit_json": {...},
  "segments": [
    {
      "p1": {"x": 10.0, "y": 5.0},
      "p2": {"x": 20.0, "y": 5.0},
      "layer": "top_copper",
      "width_mm": 0.25,
      "net_id": "VCC"
    }
  ],
  "layer": "top_copper",
  "width_mm": 0.25
}
```

Each segment must have `p1`, `p2`, and `net_id`. `layer` and `width_mm`
can be specified per-segment or as top-level defaults.

Returns: `{circuit_json, added_trace_ids}`.

### `delete_trace`

Delete a trace by `trace_id`, or by `(net_id, index)` when no `trace_id`
is known.

```json
{"circuit_json": {...}, "trace_id": "trace_abc12345"}
```

Returns: `{circuit_json, deleted, trace_id}`.

### `split_trace`

Split a trace at a given point, producing two collinear traces on the same
net. The split point must be within 0.1 mm of the trace.

```json
{
  "circuit_json": {...},
  "trace_id": "trace_abc12345",
  "point": {"x": 15.0, "y": 5.0}
}
```

Returns: `{circuit_json, original_trace_id, trace_id_a, trace_id_b, split_point}`.

### `merge_traces`

Merge two traces on the same net that share an endpoint. The shared
vertex is deduplicated.

```json
{
  "circuit_json": {...},
  "trace_ids": ["trace_aaa", "trace_bbb"]
}
```

Returns: `{circuit_json, merged_trace_id, consumed_trace_ids}`.

### `move_trace_vertex`

Move a single vertex (by 0-based index) of a trace to a new position.

```json
{
  "circuit_json": {...},
  "trace_id": "trace_abc12345",
  "vertex_index": 1,
  "new_point": {"x": 18.0, "y": 7.0}
}
```

Returns: `{circuit_json, moved, trace_id, vertex_index, new_position}`.

## CircuitJSON trace format

Traces are found under `circuit_json.pcb_traces` or `circuit_json.traces`.
Each trace has a `route` / `points` / `vertices` array of point objects:

```json
{
  "type": "pcb_trace",
  "pcb_trace_id": "trace_abc12345",
  "net_id": "VCC",
  "route": [
    {"route_type": "wire", "x": 10, "y": 5, "width": 0.25, "layer": "top_copper"},
    {"route_type": "wire", "x": 20, "y": 5, "width": 0.25, "layer": "top_copper"}
  ]
}
```

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Missing/invalid parameters |
| `NOT_FOUND` | `trace_id` not found |
| `NOT_ON_TRACE` | Split point too far from trace (> 0.1 mm) |
| `NET_MISMATCH` | Merging traces on different nets |
| `NO_SHARED_ENDPOINT` | Traces do not share an endpoint |
