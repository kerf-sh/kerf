# Buses and Differential Pairs

KiCad-style named buses group multiple signal nets under a single logical name, and differential pairs formally link a positive/negative signal pair for controlled-impedance routing.

## Data model

Two keys are added to the `pcb_board` element:

```jsonc
{
  "type": "pcb_board",
  // ...existing keys...
  "bus_definitions": [
    {
      "name": "DATA_BUS",
      "member_nets": ["DATA[7..0]", "CLK"]
    },
    {
      "name": "ADDR_BUS",
      "member_nets": ["ADDR[15..0]"]
    }
  ],
  "differential_pairs": [
    {
      "name": "USB_DP",
      "net_p_id": "USB_P",
      "net_n_id": "USB_N",
      "target_impedance_ohms": 90,
      "skew_max_mm": 0.05
    }
  ]
}
```

### `bus_definitions[].member_nets`

Each entry is either a plain net name (`"DATA0"`) or a KiCad-style slice notation:

| Syntax | Expands to |
|--------|-----------|
| `DATA[7..0]` | `DATA7, DATA6, …, DATA0` (descending) |
| `DATA[0..7]` | `DATA0, DATA1, …, DATA7` (ascending) |
| `DATA[3..3]` | `DATA3` (single bit) |
| `CLK` | `CLK` (plain name pass-through) |

Use `expand_bus` to resolve slices to individual net names before routing or net assignment.

### `differential_pairs[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Pair identifier, e.g. `"USB_DP"` |
| `net_p_id` | string | Positive signal net |
| `net_n_id` | string | Negative signal net |
| `target_impedance_ohms` | number? | Target differential impedance in Ω |
| `skew_max_mm` | number? | Max propagation-skew between P and N traces in mm |

## Tools

---

### `expand_bus`

Resolve a KiCad-style bus slice specification into individual net names.

```json
{
  "spec": "DATA[7..0]"
}
```

Returns `{ "spec": "DATA[7..0]", "nets": ["DATA7", "DATA6", ..., "DATA0"] }`.

---

### `add_bus`

Add or update a named bus definition. Overwrites existing definition with the same name.

```json
{
  "circuit_json": { "...": "..." },
  "name": "DATA_BUS",
  "member_nets": ["DATA[7..0]", "CLK"]
}
```

Returns `{ "circuit_json": { ... }, "name": "DATA_BUS" }`.

---

### `add_differential_pair`

Add or update a named differential pair. Overwrites existing pair with the same name.

```json
{
  "circuit_json": { "...": "..." },
  "name": "USB_DP",
  "net_p": "USB_P",
  "net_n": "USB_N",
  "target_impedance_ohms": 90,
  "skew_max_mm": 0.05
}
```

Returns `{ "circuit_json": { ... }, "name": "USB_DP" }`.

---

### `list_differential_pairs`

Return all differential pairs defined on the board.

```json
{
  "circuit_json": { "...": "..." }
}
```

Returns `{ "pairs": [{ "name", "net_p_id", "net_n_id", ... }, ...] }`.

---

## Worked examples

### Example 1 — 8-bit data bus with slice notation

```json
// Define the bus
{
  "circuit_json": { "type": "pcb_board", "width": 50, "height": 50 },
  "name": "DATA_BUS",
  "member_nets": ["DATA[7..0]"]
}

// Expand the slice to assign all 8 nets to a net class:
{
  "spec": "DATA[7..0]"
}
// → { "nets": ["DATA7","DATA6","DATA5","DATA4","DATA3","DATA2","DATA1","DATA0"] }
```

### Example 2 — USB differential pair with target impedance

```json
// Add USB differential pair at 90 Ω
{
  "circuit_json": { "type": "pcb_board", "width": 50, "height": 50 },
  "name": "USB_DP",
  "net_p": "USB_P",
  "net_n": "USB_N",
  "target_impedance_ohms": 90,
  "skew_max_mm": 0.05
}

// The DRC agent can now flag if routed trace width/spacing
// does not achieve ~90 Ω differential impedance on the layer stackup.

// List all pairs to verify:
{ "circuit_json": { "type": "pcb_board", "width": 50, "height": 50 } }
// → { "pairs": [{ "name": "USB_DP", "net_p_id": "USB_P", "net_n_id": "USB_N",
//                "target_impedance_ohms": 90, "skew_max_mm": 0.05 }] }
```
