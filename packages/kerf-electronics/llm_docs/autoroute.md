# kerf-electronics · autoroute.py

Automatic PCB trace routing via FreeRouting. Converts CircuitJSON to Specctra
DSN, runs the FreeRouting JAR, and parses the SES session back into routes.

## LLM tool: `autoroute_circuit`

```json
{
  "circuit_json": {...},
  "trace_width_mm": 0.2,
  "via_diameter_mm": 0.6,
  "via_drill_mm": 0.3,
  "clearance_mm": 0.2,
  "routing_layers": "1top,16bot",
  "cost_dihedral": 90.0,
  "cost_via": 50.0
}
```

All parameters except `circuit_json` are optional.

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `trace_width_mm` | 0.2 | Default trace width |
| `via_diameter_mm` | 0.6 | Via copper pad outer diameter |
| `via_drill_mm` | 0.3 | Via drill hole diameter |
| `clearance_mm` | 0.2 | Copper-to-copper clearance |
| `routing_layers` | `"1top,16bot"` | Comma-separated layer list for FreeRouting |
| `cost_dihedral` | 90.0 | Angle cost (higher = prefer 45° routing) |
| `cost_via` | 50.0 | Via cost (higher = fewer vias) |

### Returns

```json
{
  "updated_circuit": {...},
  "segments_routed": 42,
  "vias_placed": 5,
  "nets_routed": 12,
  "nets_unrouted": 0,
  "warnings": []
}
```

`updated_circuit` contains `routes`, `vias`, and `autorouted: true`.

## Pipeline

```
circuit_json
  → circuit_to_dsn()      (kerf_electronics.freerouting.dsn_writer)
  → FreeRouter.route()    (kerf_electronics.freerouting.freerouting)
  → ses_to_routes()       (kerf_electronics.freerouting.ses_reader)
  → _apply_routes_to_circuit()
```

FreeRouting is an open-source Java autorouter. The `FreeRouter` wrapper
calls the JAR synchronously.

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Missing `circuit_json` |
| `DSN_ERROR` | DSN generation failed |
| `FREEROUTE_ERROR` | FreeRouting JAR failed |
| `SES_PARSE_ERROR` | SES session parse failed |

## See also

- `routing.md` — for manual trace operations (`route_trace_segments`,
  `delete_trace`, `split_trace`, `merge_traces`, `move_trace_vertex`)
- FreeRouting source: https://github.com/freerouting/freerouting
