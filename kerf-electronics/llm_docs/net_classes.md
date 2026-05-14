# Net Classes

Net classes assign advisory trace-width, clearance, and via dimensions to groups of nets — just like KiCad's net-class system. The DRC agent enforces these; these tools only read and write the data.

## Data model

Two keys are added to the `pcb_board` element of a CircuitJSON object:

```jsonc
{
  "type": "pcb_board",
  // ...existing keys...
  "net_classes": [
    {
      "name": "Power",
      "trace_width_mm": 0.5,
      "clearance_mm": 0.25,
      "via_diameter_mm": 0.8,
      "via_drill_mm": 0.4
    },
    {
      "name": "HighSpeed",
      "trace_width_mm": 0.2,
      "clearance_mm": 0.2,
      "via_diameter_mm": 0.5,
      "via_drill_mm": 0.25,
      "target_impedance_ohms": 50
    }
  ],
  "net_class_assignments": {
    "GND":  "Power",
    "VCC":  "Power",
    "CLK":  "HighSpeed",
    "MOSI": "HighSpeed"
  },
  "net_rules": {
    "GND": { "trace_width_mm": 0.8 }
  }
}
```

- `net_classes` — user-defined or overridden classes. Builtins (Default, Power, Signal, HighSpeed, Differential) are always available without being listed here.
- `net_class_assignments` — maps net_id → class name. Unassigned nets use `Default`.
- `net_rules` — optional per-net overrides applied on top of the class rules.

### Builtin classes

| Name          | trace_width_mm | clearance_mm | via_diameter_mm | via_drill_mm | target_impedance_ohms |
|---------------|---------------|--------------|-----------------|--------------|----------------------|
| Default       | 0.25          | 0.20         | 0.60            | 0.30         | —                    |
| Power         | 0.50          | 0.25         | 0.80            | 0.40         | —                    |
| Signal        | 0.25          | 0.20         | 0.60            | 0.30         | —                    |
| HighSpeed     | 0.20          | 0.20         | 0.50            | 0.25         | 50                   |
| Differential  | 0.20          | 0.20         | 0.50            | 0.25         | 100                  |

## Tools

### `define_net_class`

Add or update a net class. Call this before assigning nets to it if the class is not one of the five builtins.

```json
{
  "circuit_json": { "...": "..." },
  "name": "HV",
  "trace_width_mm": 1.0,
  "clearance_mm": 0.8,
  "via_diameter_mm": 1.2,
  "via_drill_mm": 0.6
}
```

### `assign_net_to_class`

Assign one net to a class (builtin or user-defined).

```json
{
  "circuit_json": { "...": "..." },
  "net_id": "VCC",
  "class_name": "Power"
}
```

### `remove_net_class`

Remove a user-defined class; all nets using it fall back to `Default`.

```json
{
  "circuit_json": { "...": "..." },
  "class_name": "HV"
}
```

### `list_net_classes`

Return all classes (builtins + user-defined) and current assignments.

```json
{ "circuit_json": { "...": "..." } }
```

### `get_effective_net_rules`

Return the merged rules for a specific net (class rules + per-net overrides).

```json
{
  "circuit_json": { "...": "..." },
  "net_id": "CLK"
}
```

## Worked examples

### Example 1 — Every Power net gets 0.5 mm traces

Assign all power rails to the built-in `Power` class (no `define_net_class` call needed):

```json
// assign_net_to_class × N
{ "circuit_json": "...", "net_id": "GND",  "class_name": "Power" }
{ "circuit_json": "...", "net_id": "VCC",  "class_name": "Power" }
{ "circuit_json": "...", "net_id": "VCC3", "class_name": "Power" }
```

`get_effective_net_rules` for any of these returns `trace_width_mm: 0.5, clearance_mm: 0.25`.

### Example 2 — Every HighSpeed net gets matched impedance 50 Ω

Assign high-speed nets to the builtin `HighSpeed` class:

```json
{ "circuit_json": "...", "net_id": "CLK",  "class_name": "HighSpeed" }
{ "circuit_json": "...", "net_id": "MISO", "class_name": "HighSpeed" }
{ "circuit_json": "...", "net_id": "MOSI", "class_name": "HighSpeed" }
```

`get_effective_net_rules` returns `trace_width_mm: 0.2, target_impedance_ohms: 50`. The DRC agent uses `target_impedance_ohms` to flag traces whose width would produce a different impedance on the chosen stackup.

### Example 3 — Custom RF class at 50 Ω with narrower traces

```json
// Step 1: define
{
  "circuit_json": "...",
  "name": "RF50",
  "trace_width_mm": 0.18,
  "clearance_mm": 0.15,
  "via_diameter_mm": 0.45,
  "via_drill_mm": 0.20,
  "target_impedance_ohms": 50
}

// Step 2: assign
{ "circuit_json": "...", "net_id": "ANT_OUT", "class_name": "RF50" }
```
