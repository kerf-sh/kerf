# Hierarchical Schematics

KiCad-style hierarchical schematics allow a top-level circuit to reference child circuit files as **sub-sheet symbols**. Nets are connected between parent and child via **hierarchical labels** (scoped to the specific sheet pin) and across all sheets via **global labels** (e.g. GND, VCC).

## Data model

Three keys are added to the `pcb_board` element:

```jsonc
{
  "type": "pcb_board",
  // ...existing keys...
  "sub_sheets": [
    {
      "id": "uuid-sh1",          // generated; stable reference
      "name": "Power Supply",    // human label
      "file_id": "uuid-of-child-circuit",
      "position": [120, 80],     // schematic placement [x, y]
      "pins": [
        { "name": "VIN",  "type": "input",   "net_id": "net-vin-main"  },
        { "name": "VOUT", "type": "output",  "net_id": "net-3v3-rail"  },
        { "name": "GND",  "type": "passive", "net_id": "net-gnd-main"  }
      ]
    }
  ],
  "global_labels": [
    { "name": "GND", "net_id": "net-gnd-main" },
    { "name": "VCC", "net_id": "net-vcc-main" }
  ],
  "hierarchical_labels": [
    // Placed on CHILD sheets; sheet_id matches the parent's sub_sheets[].id
    { "name": "VOUT", "net_id": "net-vout-local", "sheet_id": "uuid-sh1" }
  ]
}
```

### `sub_sheets[].pins`

Each pin binds a **parent-side** net (`net_id`) to the **child sheet** via a matching `hierarchical_label` entry with the same `name` and `sheet_id`.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Pin label — must match a `hierarchical_label.name` in the child |
| `type` | `"input"` \| `"output"` \| `"bidirectional"` \| `"passive"` | Signal direction |
| `net_id` | string | Parent's local net identifier |

### `global_labels[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Global net name, e.g. `"GND"` |
| `net_id` | string | Local net identifier on this sheet |

Global labels with the same `name` on any sheet are **automatically equivalent** — `flatten_hierarchy` unions them regardless of depth.

### `hierarchical_labels[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Must match a pin `name` on the parent sheet symbol |
| `net_id` | string | Local net identifier on this child sheet |
| `sheet_id` | string | The `sub_sheets[].id` in the parent that owns this binding |

---

## Flattening algorithm

`flatten_hierarchy` uses **union-find** over `(sheet_path, net_id)` tuples where `sheet_path` is a slash-delimited path (e.g. `top/uuid-sh1/uuid-sh2`).

1. **Seed**: for every `global_label` on a sheet, union `(sheet_path, net_id)` with `(__global__, label_name)`.
2. **Pin binding**: for every `sub_sheets[].pins[]` entry, find the matching `hierarchical_label` (same `name` + `sheet_id`) in the child, and union `(parent_path, pin.net_id)` with `(child_path, hier_label.net_id)`.
3. **Recurse** into each child sheet.
4. **Output**: `net_groups` — a list of equivalent-net groups, each group being a list of `sheet_path::net_id` strings.

No recursive re-flattening on collision: union-find handles convergence in O(α(n)) amortised.

---

## Tools

### `add_sub_sheet`

Add a sub-sheet symbol to a parent circuit. Returns updated `circuit_json` and the generated `id`.

```json
{
  "circuit_json": { "type": "pcb_board", "..." : "..." },
  "name": "Power Supply",
  "file_id": "uuid-of-child",
  "position": [120, 80],
  "pins": [
    { "name": "VIN",  "type": "input",   "net_id": "net-vin"  },
    { "name": "VOUT", "type": "output",  "net_id": "net-3v3"  },
    { "name": "GND",  "type": "passive", "net_id": "net-gnd"  }
  ]
}
```

---

### `remove_sub_sheet`

Remove a sub-sheet symbol by `sub_sheet_id`. Also removes all `hierarchical_labels` scoped to that sheet.

```json
{
  "circuit_json": { "..." : "..." },
  "sub_sheet_id": "uuid-sh1"
}
```

---

### `add_global_label`

Add or update a global label. Calling again with the same `name` updates the `net_id`.

```json
{
  "circuit_json": { "..." : "..." },
  "name": "GND",
  "net_id": "net-gnd-main"
}
```

---

### `add_hierarchical_label`

Add or update a hierarchical label on a **child** sheet. Scoped to a specific `sheet_id`.

```json
{
  "circuit_json": { "..." : "..." },
  "name": "VOUT",
  "net_id": "net-vout-local",
  "sheet_id": "uuid-sh1"
}
```

---

### `flatten_hierarchy`

Flatten a hierarchy into net equivalence groups.

```json
{
  "top_circuit_json": { "type": "pcb_board", "..." : "..." },
  "children": {
    "uuid-of-child-1": { "type": "pcb_board", "..." : "..." },
    "uuid-of-child-2": { "type": "pcb_board", "..." : "..." }
  }
}
```

Returns:

```json
{
  "net_groups": [
    ["top::net-gnd-main", "top/uuid-sh1::net-gnd-local", "__global__::GND"],
    ["top::net-3v3",      "top/uuid-sh1::net-vout-local"]
  ]
}
```

---

### `validate_hierarchy`

Validate a hierarchy and return all errors.

```json
{
  "top_circuit_json": { "..." : "..." },
  "children": { "uuid-child": { "..." : "..." } }
}
```

Returns `{ "ok": true, "errors": [] }` or `{ "ok": false, "errors": ["..."] }`.

Error categories:
- `referenced file_id "..." not found in children`
- `pin "X" has no matching hierarchical_label in child circuit`
- `hierarchical_label "X" has no matching pin on parent sheet symbol`
- `global label "X" has conflicting net_ids: "..." vs "..."`

---

## Examples

### Example 1 — Power supply sub-sheet

A main board (`main.circuit.tsx`) instantiates a power-supply sub-sheet (`psu.circuit.tsx`).

**Main board (parent)**:

```json
{
  "type": "pcb_board",
  "sub_sheets": [{
    "id": "sh-psu",
    "name": "Power Supply",
    "file_id": "uuid-psu",
    "position": [200, 100],
    "pins": [
      { "name": "VIN",  "type": "input",   "net_id": "net-vin"  },
      { "name": "VOUT", "type": "output",  "net_id": "net-3v3"  },
      { "name": "GND",  "type": "passive", "net_id": "net-gnd"  }
    ]
  }],
  "global_labels": [
    { "name": "GND", "net_id": "net-gnd" }
  ]
}
```

**PSU child** (`uuid-psu`):

```json
{
  "type": "pcb_board",
  "hierarchical_labels": [
    { "name": "VIN",  "net_id": "psu-vin",   "sheet_id": "sh-psu" },
    { "name": "VOUT", "net_id": "psu-vout",  "sheet_id": "sh-psu" },
    { "name": "GND",  "net_id": "psu-gnd",   "sheet_id": "sh-psu" }
  ],
  "global_labels": [
    { "name": "GND", "net_id": "psu-gnd" }
  ]
}
```

After `flatten_hierarchy`:
- `top::net-vin` ↔ `top/sh-psu::psu-vin`
- `top::net-3v3` ↔ `top/sh-psu::psu-vout`
- `top::net-gnd` ↔ `top/sh-psu::psu-gnd` ↔ `__global__::GND`

---

### Example 2 — Three-tier hierarchy (main → mid → leaf)

```
main.circuit.tsx
 └── comms.circuit.tsx   (file_id: uuid-comms)
      └── uart.circuit.tsx  (file_id: uuid-uart)
```

**main** has `sub_sheets: [{ id: "sh-comms", file_id: "uuid-comms", pins: [{ name: "TX", ... }] }]`

**comms** has `hierarchical_labels: [{ name: "TX", sheet_id: "sh-comms", net_id: "comms-tx" }]` and `sub_sheets: [{ id: "sh-uart", file_id: "uuid-uart", pins: [{ name: "TX", ... }] }]`

**uart** has `hierarchical_labels: [{ name: "TX", sheet_id: "sh-uart", net_id: "uart-tx" }]`

`flatten_hierarchy(main, { "uuid-comms": comms, "uuid-uart": uart })` produces a single group containing `top::net-tx`, `top/sh-comms::comms-tx`, and `top/sh-comms/sh-uart::uart-tx`.

All three are electrically equivalent — one net.
