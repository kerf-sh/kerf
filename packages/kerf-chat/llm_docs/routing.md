# Manual Trace Routing

Manual trace routing lets the LLM (or user) define precise copper trace paths between pads/nets in a PCB layout. Use it when you need exact control over routing geometry — for controlled-impedance lines, differential pairs, short high-current paths, or any situation where the automatic FreeRouting autorouter (`autoroute_circuit`) produces unsatisfactory results. Manual and automatic routing coexist: you can autoroute most of the board and then refine specific nets manually.

## CircuitJSON trace shape

Traces live in `circuit_json["pcb_traces"]` (or `"traces"` for older boards). Each entry:

```jsonc
{
  "type": "pcb_trace",
  "pcb_trace_id": "trace_a1b2c3d4",
  "net_id": "GND",
  "route": [
    {"route_type": "wire", "x": 12.5, "y": 8.0,  "width": 0.25, "layer": "top_copper"},
    {"route_type": "wire", "x": 15.0, "y": 8.0,  "width": 0.25, "layer": "top_copper"},
    {"route_type": "wire", "x": 15.0, "y": 5.5,  "width": 0.25, "layer": "top_copper"}
  ]
}
```

- `route`: ordered vertices; minimum 2.
- `net_id`: must match an existing net (a `source_net` or `pcb_net` entry in the board).
- `width` per route point (mm); typically constant per trace.
- `layer`: standard layer names — `top_copper`, `bottom_copper`, `inner1_copper` … `inner30_copper`.

Layer changes within a single trace (via stubs) are supported: insert a `{"route_type": "via", "x", "y", "from_layer", "to_layer", "hole_diameter"}` point between the copper segments.

## Routing modes (frontend)

The `RouteTool` in `PCBView.jsx` supports three modes (persisted in `localStorage`):

| Mode | Angles | Use case |
|------|--------|----------|
| `orthogonal` | 90° only | default, dense digital boards |
| `45` | 90° + 45° bends | IPC-preferred, impedance-critical |
| `free` | arbitrary | RF, flex, non-rectilinear boards |

The pure JS helpers for these modes live in `src/lib/pcbRouting.js`:

- `orthogonalSnap(p1, p2, lastDirection?)` → `{p2_snapped, direction}` — snaps endpoint to H or V.
- `corner45(p1, p2)` → `[mid, p2]` or `[p2]` — 45°-preferred two-segment route.
- `freeRoute(p1, p2)` → `[p2]` — straight segment, no constraint.
- `pickRoutingMode(mode, p1, p2, lastDirection?)` — dispatches to the above.
- `splitTraceAtPoint(trace, point, tolerance)` → `[traceA, traceB] | null`
- `detectTJunction(traces, vertex, tolerance)` → `traceId | null`
- `mergeTraces(traces, tolerance)` → merged trace array

Click to start at a pad/net, click to add vertices, double-click or press Enter to finish, Esc to cancel.

## Tools

All tools accept `circuit_json` (parsed board object) and return an updated `circuit_json`. Apply the returned object via `write_file` / `edit_file` to persist.

---

### `route_trace_segments`

Append one or more new polyline traces.

```json
{
  "circuit_json": { "...": "..." },
  "layer": "top_copper",
  "width_mm": 0.25,
  "net_id": "GND",
  "segments": [
    {
      "p1": {"x": 5.0, "y": 10.0},
      "p2": {"x": 5.0, "y": 5.0},
      "net_id": "GND"
    },
    {
      "p1": {"x": 5.0, "y": 5.0},
      "p2": {"x": 12.0, "y": 5.0}
    }
  ]
}
```

Top-level `layer`, `width_mm`, and `net_id` are defaults; per-segment values override them.

Returns `{circuit_json, added_trace_ids: [...]}`.

---

### `split_trace`

Insert a vertex into an existing trace at `point`, splitting it into two collinear traces on the same net. Useful for adding a T-junction or detouring around a new obstacle. `point` must be within 0.1 mm of a segment.

```json
{
  "circuit_json": { "...": "..." },
  "trace_id": "trace_a1b2c3d4",
  "point": {"x": 8.0, "y": 5.0}
}
```

Returns `{circuit_json, original_trace_id, trace_id_a, trace_id_b, split_point}`.

---

### `merge_traces`

Merge two traces that share an endpoint on the same net into a single trace, removing the duplicate vertex. The pair must have the same `net_id`; traces on different nets are refused.

```json
{
  "circuit_json": { "...": "..." },
  "trace_ids": ["trace_abc", "trace_def"]
}
```

Returns `{circuit_json, merged_trace_id, consumed_trace_ids}`.

---

### `move_trace_vertex`

Nudge a single vertex of a trace to a new position. `vertex_index` is zero-based into the `route` array.

```json
{
  "circuit_json": { "...": "..." },
  "trace_id": "trace_a1b2c3d4",
  "vertex_index": 1,
  "new_point": {"x": 14.0, "y": 5.0}
}
```

Returns `{circuit_json, moved, trace_id, vertex_index, new_position}`.

---

### `delete_trace`

Remove a trace by `trace_id`.

```json
{
  "circuit_json": { "...": "..." },
  "trace_id": "trace_a1b2c3d4"
}
```

Returns `{circuit_json, deleted, trace_id}`.

## Common workflows

**Add a single-segment trace on GND:**
```json
route_trace_segments({circuit_json, net_id:"GND", layer:"top_copper", width_mm:0.5,
  segments:[{p1:{x:0,y:0}, p2:{x:10,y:0}}]})
```

**Insert a T-junction at a midpoint:**
1. Call `split_trace` at the desired junction point → get `trace_id_a`, `trace_id_b`.
2. Call `route_trace_segments` starting at the split point to branch the new net segment.

**Reroute around a new via:**
1. `split_trace` on the affected trace at both sides of the via.
2. `move_trace_vertex` to add the detour vertices.
3. `delete_trace` the stub between the two split points.
4. `route_trace_segments` the new path around the via.
