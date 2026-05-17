# kerf-electronics · pcb_drc.py

PCB Design Rule Check (DRC). Pure-Python implementation that mirrors the
frontend `pcbDRC.js` exactly so LLM tools and overlay rendering produce
identical results.

## LLM tools

### `run_pcb_drc`

Run all DRC checks on a CircuitJSON board array.

```json
{
  "circuit_json": [
    {"type": "pcb_board", "width": 50, "height": 40},
    {"type": "pcb_trace", "pcb_trace_id": "t1", "route": [...], "net_id": "VCC"},
    {"type": "pcb_via", "x": 10, "y": 10, "outer_diameter": 0.6, "hole_diameter": 0.3}
  ]
}
```

Returns:

```json
{
  "errors": [
    {
      "kind": "trace_too_narrow",
      "severity": "error",
      "message": "Trace width 0.10 mm is below minimum 0.15 mm",
      "x": 5.0, "y": 3.0,
      "trace_id": "t1"
    }
  ],
  "warnings": [
    {
      "kind": "silk_on_pad",
      "severity": "warning",
      "message": "Silkscreen text may overlap pad at (12.00, 8.00)",
      "x": 11.9, "y": 8.1
    }
  ],
  "summary": {"error_count": 1, "warning_count": 1}
}
```

### `set_drc_rule`

Update a single DRC rule on the `pcb_board` element. Returns the modified
`circuit_json`.

```json
{
  "circuit_json": [...],
  "rule_name": "min_trace_width_mm",
  "value": 0.2
}
```

Valid rule names and defaults:

| Rule | Default | Unit |
|---|---|---|
| `min_trace_width_mm` | 0.15 | mm |
| `min_via_clearance_mm` | 0.10 | mm |
| `min_drill_spacing_mm` | 0.20 | mm |
| `min_copper_to_edge_mm` | 0.30 | mm |
| `silk_on_pad_tolerance` | 0.05 | mm |

## Checks performed

| Check | Severity | Description |
|---|---|---|
| `trace_too_narrow` | error | Trace width below `min_trace_width_mm` |
| `via_clearance` | error | Gap between via pads below `min_via_clearance_mm` |
| `drill_spacing` | error | Drill hole edge-to-edge below `min_drill_spacing_mm` |
| `dangling_trace` | error | Trace endpoint not connected to pad or other trace |
| `net_short` | error | Copper path connects two different net IDs |
| `silk_on_pad` | warning | Silkscreen text overlaps a pad |
| `copper_to_edge` | warning | Copper item within `min_copper_to_edge_mm` of board edge |

## Net-short detection

Union-Find (path-compressed) algorithm. All pads with the same coordinates
are merged. Traces union their start-pad and end-pad clusters. Clusters with
more than one distinct `net_id` are reported as shorts.

## Standards reference

- IPC-2221B: Generic Standard on Printed Board Design
- IPC-7711/7721: Rework and Repair of Printed Boards
