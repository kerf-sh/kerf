# Pad Solder Mask / Paste Overrides

KiCad-style per-pad solder mask and solder-paste aperture overrides allow fine-tuning of individual pad openings without changing board-level defaults. Useful for QFN exposed thermal pads (no mask), fine-pitch parts (reduced paste), and custom aperture shapes.

## Data model

Per-pad override keys added to `pcb_smtpad` elements:

```jsonc
{
  "type": "pcb_smtpad",
  "pcb_smtpad_id": "U1_PAD6",
  "x": 10.0,
  "y": 20.0,
  "width": 2.0,
  "height": 3.0,
  "mask_override": {
    "expansion_mm": 0.25
  },
  "paste_override": {
    "scale": 0.85,
    "offset_mm": 0.02,
    "polygon": [[0, 0], [2, 0], [2, 3], [0, 3]]
  }
}
```

Board-level defaults on `pcb_board.pad_defaults`:

```jsonc
{
  "type": "pcb_board",
  "pad_defaults": {
    "mask_expansion_mm": 0.05,
    "paste_scale": 1.0
  }
}
```

### `mask_override`

| Field | Type | Description |
|-------|------|-------------|
| `expansion_mm` | number | How much to expand the mask aperture (positive = remove more mask). Applied uniformly in all directions. |

### `paste_override`

| Field | Type | Description |
|-------|------|-------------|
| `scale` | number? | Scale factor applied to pad width/height. 0.5 = half-size aperture. |
| `offset_mm` | number? | Shift the aperture center by [x, y] mm. |
| `polygon` | array? | Custom aperture as array of `[x, y]` points (minimum 3). Takes precedence over scale/offset. |

## Tools

---

### `set_pad_mask_override`

Set or update the solder-mask aperture expansion for a specific SMT pad.

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "expansion_mm": 0.25
}
```

**Response:**

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "expansion_mm": 0.25
}
```

---

### `set_pad_paste_override`

Set or update the solder-paste stencil aperture for a specific SMT pad.

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "scale": 0.85
}
```

Or with offset:

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "scale": 0.8,
  "offset_mm": 0.02
}
```

Or with custom polygon:

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "polygon": [[0, 0], [2, 0], [2, 3], [0, 3]]
}
```

**Response:**

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6",
  "paste_override": { "scale": 0.85 }
}
```

---

### `clear_pad_overrides`

Remove both `mask_override` and `paste_override` from a pad, reverting to board defaults.

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6"
}
```

**Response:**

```json
{
  "circuit_json": { "...": "..." },
  "pad_id": "U1_PAD6"
}
```

---

## Worked examples

### Example 1 — QFN exposed thermal pad with no solder mask

Many QFN packages have a large exposed thermal pad on the bottom. This pad must not have solder mask covering it, or the part will not solder properly.

```json
// Set a large mask expansion to open the mask window fully
{
  "circuit_json": { "type": "pcb_board", "pcb_smtpad": [
    { "pcb_smtpad_id": "U1_THERMAL", "x": 0, "y": 0, "width": 5, "height": 5 }
  ]},
  "pad_id": "U1_THERMAL",
  "expansion_mm": 0.5
}
// Result: mask aperture is 5mm + 2*0.5mm = 6mm square
```

### Example 2 — Fine-pitch BGA with reduced paste

For fine-pitch BGA or 0402 components, reducing solder paste volume helps prevent bridging. Scale paste apertures to 60% of pad size.

```json
// Reduce paste to 60% for all fine-pitch pads
{
  "circuit_json": { "type": "pcb_board", "pcb_smtpad": [
    { "pcb_smtpad_id": "U1_BGA1", "x": 5, "y": 5, "width": 0.4, "height": 0.4 },
    { "pcb_smtpad_id": "U1_BGA2", "x": 5.5, "y": 5, "width": 0.4, "height": 0.4 }
  ]},
  "pad_id": "U1_BGA1",
  "scale": 0.6
}
// Result: paste aperture is 0.4*0.6 = 0.24mm square
```