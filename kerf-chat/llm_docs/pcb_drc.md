# PCB Design Rule Check (DRC)

Use `run_pcb_drc` to validate a CircuitJSON board against manufacturing and
electrical rules. Use `set_drc_rule` to tighten or loosen individual rules
before running DRC.

## Tools

### `run_pcb_drc`

Runs all DRC checks and returns errors, warnings, and a summary count.

```json
{
  "circuit_json": [ ...AnyCircuitElement[] ]
}
```

**Response:**

```json
{
  "errors": [
    {
      "kind": "trace_too_narrow",
      "severity": "error",
      "message": "Trace width 0.100 mm is below minimum 0.150 mm",
      "x": 7.5,
      "y": 5.0,
      "trace_id": "t1"
    }
  ],
  "warnings": [
    {
      "kind": "copper_to_edge",
      "severity": "warning",
      "message": "Trace is 0.100 mm from board edge (min 0.300 mm)",
      "x": 0.1,
      "y": 25.0
    }
  ],
  "summary": {
    "error_count": 1,
    "warning_count": 1
  }
}
```

### `set_drc_rule`

Updates a single rule on `board.drc_rules` and returns the modified
`circuit_json`. Persist the returned array to apply the change.

```json
{
  "circuit_json": [ ...AnyCircuitElement[] ],
  "rule_name": "min_trace_width_mm",
  "value": 0.20
}
```

**Response:**

```json
{
  "rule_name": "min_trace_width_mm",
  "value": 0.20,
  "circuit_json": [ ...updated array... ]
}
```

## DRC Rules

All distance values are in **millimetres**.

| Rule | Default | Description |
|------|---------|-------------|
| `min_trace_width_mm` | 0.15 | Narrowest allowed copper trace. Any trace thinner than this is flagged as `trace_too_narrow` (error). |
| `min_via_clearance_mm` | 0.10 | Minimum gap between the outer pads of any two vias. Violations are `via_clearance` (error). |
| `min_drill_spacing_mm` | 0.20 | Minimum edge-to-edge distance between drill holes. Violations are `drill_spacing` (error). |
| `min_copper_to_edge_mm` | 0.30 | Copper (traces, pads, vias) must stay this far from the board outline. Violations are `copper_to_edge` (warning). |
| `silk_on_pad_tolerance` | 0.05 | How much a silkscreen element may intrude into a pad area before a `silk_on_pad` warning is raised. |

## Check Descriptions

### `trace_too_narrow` (error)
The trace's `route_thickness_mm` is below `min_trace_width_mm`. Thin traces
are fragile, have high resistance, and may not survive the etching process at
many fabs.

### `via_clearance` (error)
Two vias are closer together than `min_via_clearance_mm` (measured from outer
annular ring edge to outer annular ring edge). May cause short circuits or
mechanical stress.

### `drill_spacing` (error)
Two drill holes are closer than `min_drill_spacing_mm` edge-to-edge. Overlapping
drills destroy the PCB laminate between holes.

### `dangling_trace` (error)
A trace endpoint is not coincident with any pad position and is not connected to
another trace endpoint. Dangling traces often indicate a routing mistake — a
connection that was started but never completed.

### `net_short` (error)
A continuous copper path (via traces) connects pads that belong to different
nets. This is an electrical short that will cause incorrect circuit behaviour.
The message names all shorted nets.

### `silk_on_pad` (warning)
A silkscreen text anchor overlaps a pad within the `silk_on_pad_tolerance`.
Silk over copper pads can cause soldering problems and is flagged as advisory.

### `copper_to_edge` (warning)
A copper element is closer to the board outline than `min_copper_to_edge_mm`.
This is a fabrication advisory — routing copper to the board edge risks
delamination during depanelling.

## Workflow Example

```
1. run_pcb_drc({ circuit_json }) → review errors/warnings
2. set_drc_rule({ circuit_json, rule_name: "min_trace_width_mm", value: 0.20 })
   → use returned circuit_json for subsequent calls
3. run_pcb_drc({ circuit_json: updated }) → re-check with stricter rule
```

## Entry Points in Code

- **JS engine:** `src/lib/pcbDRC.js` — `runDRC(circuitJson)` (pure, no DOM).
- **Python tool:** `backend/tools/pcb_drc.py` — `_run_drc_on_circuit(list)`.
- Both share the same DEFAULT_RULES values and check logic.
