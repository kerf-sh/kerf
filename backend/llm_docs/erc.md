# Electrical Rules Check (ERC)

Use `run_erc` to validate a CircuitJSON schematic. It returns the same
structure for every check: `{ "errors": [...], "warnings": [...] }`.

Each entry has:
| field | type | notes |
|---|---|---|
| `kind` | string | rule name — see below |
| `severity` | `"error"` \| `"warning"` | |
| `message` | string | human-readable description |
| `component_id` | string? | `source_component_id` of the offending component |
| `port_id` | string? | `source_port_id` of the offending port |
| `net_id` | string? | `source_net_id` of the offending net |

---

## Rules

### `unconnected_pin` — error
Every `source_port` must be touched by at least one `source_trace`.
A port that appears in no trace's `connected_source_port_ids` is flagged.

**Common cause:** forgot to route a pin; stub left after deleting a trace.

---

### `duplicate_refdes` — error
No two `source_component` elements may share the same `name`
(reference designator).

**Common cause:** copy-pasting a component without renaming it.

---

### `conflicting_net_label` — error
Two `source_net` elements that union-find merges into the same net
(via shared traces) but carry different names.

**Common cause:** renaming one side of a net junction; two labels
manually placed on the same wire.

---

### `output_to_output` — error
Two `source_port` elements with `pin_type = "output"` appear on the
same trace. Ports with `electrical_function = "open_collector"` or
`"open_drain"` are explicitly excluded (wired-OR is valid).

**Common cause:** two active drivers short-circuited; accidentally
connecting TX lines of two UARTs.

---

### `missing_power` — error
A `source_net` whose name matches a power-net pattern
(`VCC`, `VDD`, `VSS`, `GND`, `VBAT`, `V<n>V`, `PWR`) or has
`is_power: true` is referenced but no `source_port` with
`pin_type = "power"` / `"power_out"` / `"supply"` sources it.

**Common cause:** added a power flag symbol but forgot the PWR_FLAG /
power-port component; missing voltage regulator in the netlist.

---

### `pin_direction_mismatch` — warning
Two or more input-only ports are wired together with no driver
(no output, power, or passive port) on the same trace.

**Common cause:** connecting the output of one buffer to the output of
another (where both are actually inputs), or a disconnected signal
accidentally touching another input.

---

### `floating_net` — warning
A net that has exactly one port connected to it — the trace goes
nowhere. Almost always a bug.

**Common cause:** dangling wire stub; partially routed signal.

---

### `bidirectional_promiscuity` — warning
More than 3 `source_port` elements with `pin_type = "bidirectional"`
share the same net. This is legal but suggests a bus (SPI, I²C, etc.)
should be explicitly modelled as such.

**Common cause:** many I²C devices on one SDA line without a bus
abstraction; shared data bus modelled as individual traces.

---

## Example circuit with violations

```json
[
  { "type": "source_component", "source_component_id": "c1", "name": "U1" },
  { "type": "source_component", "source_component_id": "c2", "name": "U1" },

  { "type": "source_port", "source_port_id": "p1",
    "source_component_id": "c1", "name": "OUT", "pin_type": "output" },
  { "type": "source_port", "source_port_id": "p2",
    "source_component_id": "c2", "name": "OUT", "pin_type": "output" },
  { "type": "source_port", "source_port_id": "p3",
    "source_component_id": "c1", "name": "IN",  "pin_type": "input" },

  { "type": "source_trace", "source_trace_id": "t1",
    "connected_source_port_ids": ["p1", "p2"] },

  { "type": "source_net", "source_net_id": "n1", "name": "VCC", "is_power": true }
]
```

Expected ERC output:

```json
{
  "errors": [
    {
      "kind": "duplicate_refdes",
      "severity": "error",
      "message": "Duplicate reference designator \"U1\" (components \"c1\" and \"c2\")",
      "component_id": "c2"
    },
    {
      "kind": "output_to_output",
      "severity": "error",
      "message": "Output pin \"OUT\" tied to output pin \"OUT\"",
      "port_id": "p2"
    },
    {
      "kind": "unconnected_pin",
      "severity": "error",
      "message": "Pin \"IN\" on component \"c1\" is unconnected",
      "component_id": "c1",
      "port_id": "p3"
    },
    {
      "kind": "missing_power",
      "severity": "error",
      "message": "Power net \"VCC\" is referenced but never sourced by a power/supply pin",
      "net_id": "n1"
    }
  ],
  "warnings": [
    {
      "kind": "floating_net",
      "severity": "warning",
      "message": "Net (root \"p1\") has only one connected port … — possible floating wire"
    }
  ]
}
```

*(The `floating_net` arises because the output-to-output trace only
connects two ports that share a root, but from the trace-port count
perspective one side is isolated. In a corrected schematic, replacing
one output with an input resolves both the `output_to_output` error
and the structural ambiguity.)*

---

## Tool signature

```json
{
  "name": "run_erc",
  "input": { "circuit_json": [ /* AnyCircuitElement[] */ ] },
  "output": {
    "errors":   [ { "kind": "…", "severity": "error",   "message": "…", … } ],
    "warnings": [ { "kind": "…", "severity": "warning", "message": "…", … } ]
  }
}
```
