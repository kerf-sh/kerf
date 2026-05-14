# Manual Trace Routing

Manual trace routing lets the LLM (or user) define precise copper trace paths between pads/nets in a PCB layout. Use it when you need exact control over routing geometry — for controlled-impedance lines, differential pairs, short high-current paths, or any situation where the automatic FreeRouting autorouter (`autoroute_circuit`) produces unsatisfactory results. Manual and automatic routing coexist: you can autoroute most of the board and then refine specific nets manually.

## Data model

Traces are stored in the `traces` array of a CircuitJSON board. Each trace entry:

```jsonc
{
  "points": [
    {"x": 12.5, "y": 8.0, "layer": "top_copper"},
    {"x": 15.0, "y": 8.0, "layer": "top_copper"},
    {"x": 15.0, "y": 5.5, "layer": "top_copper"}
  ],
  "net_id": "GND",
  "width_mm": 0.25
}
```

- `points`: ordered list of vertices; minimum 2.
- `net_id`: must match an existing net in the circuit's `source_net` entries.
- `width_mm`: copper width in mm; defaults to 0.25 if omitted.
- `layer`: per-point layer allows layer-change via vias (advanced); for single-layer traces all points share the same layer.

The `appendTrace` helper in `circuitTSX.js` handles simple two-point traces. For multi-vertex polylines use `route_trace_segments`.

## Tools

### `route_trace_segments`

Add one or more manually-routed polyline traces.

```json
{
  "file_id": "my-board.circuit.tsx",
  "segments": [
    {
      "net_id": "GND",
      "width_mm": 0.5,
      "layer": "top_copper",
      "points": [
        {"x": 5.0, "y": 10.0},
        {"x": 5.0, "y": 5.0},
        {"x": 12.0, "y": 5.0}
      ]
    }
  ]
}
```

### `delete_trace`

Remove a trace by ID or by net + index.

```json
{"file_id": "my-board.circuit.tsx", "trace_id": "trace_abc123"}
// or
{"file_id": "my-board.circuit.tsx", "net_id": "GND", "index": 2}
```

### `split_trace`

Insert a vertex into an existing trace, splitting it into two collinear traces on the same net. Useful for adding a T-junction or detouring around a new obstacle.

```json
{
  "file_id": "my-board.circuit.tsx",
  "trace_id": "trace_abc123",
  "split_point": {"x": 8.0, "y": 5.0}
}
```

### `merge_traces`

Merge two traces that share an endpoint on the same net into a single trace.

```json
{
  "file_id": "my-board.circuit.tsx",
  "trace_id_a": "trace_abc",
  "trace_id_b": "trace_def"
}
```

### `move_trace_vertex`

Nudge a single vertex of a trace to a new position.

```json
{
  "file_id": "my-board.circuit.tsx",
  "trace_id": "trace_abc123",
  "vertex_index": 1,
  "new_x": 14.0,
  "new_y": 5.0
}
```

## Routing modes (frontend)

The frontend `RouteTool` in `PCBView.jsx` supports three routing modes (persisted in localStorage):

- **Orthogonal** (90° only) — default.
- **45°** — orthogonal segments with 45° bends.
- **Free** — arbitrary angles (RF, odd geometries).

Click to start at a pad/net, click to add vertices, double-click or press Enter to finish, Esc to cancel.
