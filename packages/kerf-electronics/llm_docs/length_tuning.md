# Trace Length Tuning and Differential-Pair Skew Compensation

KiCad-style meander insertion to bring a trace to a target length, and skew matching for differential pairs.

## Data model

### `pcb_trace.target_length_mm`

An optional annotation added to any `pcb_trace` element in CircuitJSON:

```jsonc
{
  "type": "pcb_trace",
  "id": "ddr_dq0",
  "net_id": "DDR_DQ0",
  "points": [{ "x": 10, "y": 5 }, { "x": 50, "y": 5 }],
  "target_length_mm": 65.0
}
```

Set this with `set_trace_target_length` before calling `tune_trace_to_target`.

### `board.differential_pairs` (from buses agent)

Length-tuning reads `board.differential_pairs` defensively — the field may not exist if the buses agent has not yet run.  Define pairs with the buses agent's `add_differential_pair` tool.

```jsonc
{
  "type": "pcb_board",
  "differential_pairs": [
    {
      "name": "USB_DP",
      "net_p_id": "USB_P",
      "net_n_id": "USB_N",
      "skew_max_mm": 0.05
    }
  ]
}
```

## Meander styles

| Style | Shape | Extra length per period | Best for |
|-------|-------|------------------------|----------|
| `serpentine` | Square wave (perpendicular teeth) | ≈ 2 × amplitude | Long PCB runs, DDR address lines |
| `accordion` | Triangle wave (diagonal teeth) | 2 × hypotenuse − period | Compact areas |
| `trombone` | Single U-turn out-and-back detour | 4 × amplitude + 2 × run | Endpoint near board edge |

`amplitude_mm` controls tooth half-height; `period_mm` controls tooth spacing (serpentine and accordion).

## Tools

---

### `set_trace_target_length`

Annotate a trace with its desired final length. Must be called before `tune_trace_to_target`.

```json
{
  "circuit_json": { "...": "..." },
  "trace_id": "ddr_dq0",
  "target_length_mm": 65.0
}
```

Returns `{ "circuit_json": {...}, "trace_id": "ddr_dq0", "target_length_mm": 65.0 }`.

---

### `tune_trace_to_target`

Apply a meander to the longest straight segment of a trace so its total length reaches `target_length_mm`. The trace must already have `target_length_mm` set.

```json
{
  "circuit_json": { "...": "..." },
  "trace_id": "ddr_dq0",
  "style": "serpentine",
  "amplitude_mm": 0.3
}
```

Returns `{ "circuit_json": {...}, "trace_id": "ddr_dq0", "new_length_mm": 65.02 }`.

Parameters:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `circuit_json` | object\|array | — | CircuitJSON board or element list |
| `trace_id` | string | — | `id` of the `pcb_trace` |
| `style` | string | `"serpentine"` | `"serpentine"` \| `"accordion"` \| `"trombone"` |
| `amplitude_mm` | number | `0.5` | Half-amplitude of meander teeth |

---

### `report_diff_pair_skew`

Report the current propagation-skew between the P and N traces of a named differential pair.

```json
{
  "circuit_json": { "...": "..." },
  "pair_name": "USB_DP"
}
```

Returns `{ "pair_name": "USB_DP", "length_p": 32.1, "length_n": 30.4, "delta_mm": 1.7 }`.

---

### `match_diff_pair`

Lengthen the shorter trace of a differential pair to bring it within `skew_max_mm` of the longer. Does nothing if the pair is already within tolerance.

```json
{
  "circuit_json": { "...": "..." },
  "pair_name": "USB_DP",
  "style": "serpentine",
  "amplitude_mm": 0.2,
  "skew_max_mm": 0.05
}
```

Returns `{ "circuit_json": {...}, "tuned_net": "USB_N", "delta_mm": 0.03 }`.
`tuned_net` is `null` if the pair was already within tolerance.

Parameters:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `skew_max_mm` | number | pair definition → `0.05` | Override skew tolerance |

---

## Workflow

### Single-trace length tuning

1. `set_trace_target_length` — annotate the trace.
2. `tune_trace_to_target` — insert the meander.
3. Optionally run DRC to confirm no clearance violations.

### Differential-pair skew compensation

1. `report_diff_pair_skew` — inspect current state.
2. `match_diff_pair` — lengthen the shorter trace.
3. `report_diff_pair_skew` — verify delta is within budget.

---

## Worked examples

### Example 1 — DDR4 address line length tuning

DDR4 requires address lines to be length-matched within ±25 ps (≈ 3.5 mm at typical PCB dielectric). One address line routes short because of a via detour.

```json
// Step 1: check current skew on DDR_ADDR pair
{
  "circuit_json": { "...": "..." },
  "pair_name": "DDR_ADDR_P"
}
// → { "length_p": 48.2, "length_n": 44.7, "delta_mm": 3.5 }

// Step 2: annotate the N trace with the target length
{
  "circuit_json": { "...": "..." },
  "trace_id": "addr_n_main",
  "target_length_mm": 48.2
}

// Step 3: apply serpentine meander (DDR fanout area has room for 0.4 mm amplitude)
{
  "circuit_json": { "...": "..." },
  "trace_id": "addr_n_main",
  "style": "serpentine",
  "amplitude_mm": 0.4
}
// → { "new_length_mm": 48.21 }
```

### Example 2 — USB 2.0 differential-pair skew compensation

USB 2.0 full-speed requires D+/D− skew < 500 ps (≈ 70 mm); high-speed (HS) requires < 25 ps (≈ 3.5 mm). Using `match_diff_pair` automates this.

```json
// Check the current skew
{
  "circuit_json": { "...": "..." },
  "pair_name": "USB_DP"
}
// → { "length_p": 31.8, "length_n": 28.5, "delta_mm": 3.3 }

// Compensate in one call — use trombone style since the USB_N trace
// exits near a board corner and has limited lateral clearance
{
  "circuit_json": { "...": "..." },
  "pair_name": "USB_DP",
  "style": "trombone",
  "amplitude_mm": 0.6,
  "skew_max_mm": 0.05
}
// → { "tuned_net": "USB_N", "delta_mm": 0.02 }

// Verify
{
  "circuit_json": { "...": "..." },
  "pair_name": "USB_DP"
}
// → { "length_p": 31.8, "length_n": 31.78, "delta_mm": 0.02 }
```
