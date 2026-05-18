# kerf-packaging — Dieline / flat-pattern for folding carton + corrugated

Generates 2-D dielines (flat cut-and-score patterns) for standard ECMA box styles
and folds them into 3-D carton shapes.  Built on the shipped DXF writer (T-7).

## Supported ECMA styles

| Style | Name | Use case |
|-------|------|----------|
| C02   | Regular Slotted Container (RSC) | Corrugated shipping boxes, mailers |
| A10   | One-piece tray / folder | Retail trays, food packaging |
| B03   | Counter display box (tuck front) | POS / shelf display |

## Tools

### `packaging_dieline_generate`

Generate a parametric ECMA dieline.  Returns blank dimensions, panel names,
cut/fold line counts, and metadata.

```json
{
  "style": "C02",
  "length": 300,
  "width": 200,
  "depth": 150,
  "board_t": 0.5,
  "material": "flute_c"
}
```

### `packaging_dieline_to_dxf`

Generate a dieline and export directly to DXF text.  Layers:
- `cut`   (red, ACI 1) — outer cut boundary
- `fold`  (cyan, ACI 4) — crease / fold lines
- `score` (yellow, ACI 2) — partial-cut score lines

```json
{
  "style": "C02",
  "length": 300,
  "width": 200,
  "depth": 150,
  "dxf_version": "R2004"
}
```

Returns `{ "dxf": "...", "blank_width_mm": ..., "blank_height_mm": ... }`.

### `packaging_fold_preview`

Fold the dieline into a 3-D shape.  Returns per-panel 3-D vertex positions,
bounding box, and a `is_closed` flag.

```json
{
  "style":  "C02",
  "length": 300,
  "width":  200,
  "depth":  150,
  "fold_angle": 90
}
```

`fold_angle` can be varied from 0 (flat) to 90 (fully assembled) for animation frames.

## Python API

```python
from kerf_packaging.ecma_generators import ecma_c02_rsc
from kerf_packaging.fold import fold_dieline

# Generate dieline
d = ecma_c02_rsc(length=300, width=200, depth=150)
print(d.width, d.height)   # blank dimensions in mm

# Export to DXF
from kerf_imports.dxf_writer import dxf_export
dxf_text = dxf_export(d.to_drawing_dict())

# Fold to 3-D
result = fold_dieline(d)
print(result.is_closed)      # True for a fully assembled RSC
print(result.bounding_box)   # ((x_min, y_min, z_min), (x_max, y_max, z_max))
```

## ECMA C-02 RSC dimensions

For internal dimensions L × W × D:

```
blank_width  = 2L + 2W + joint  (joint default = 15 mm)
blank_height = D + W            (flap height = W/2 top + W/2 bottom)
```

Panel layout (left→right):
```
[left | front | right | back | joint]
     ↕ fold lines (vertical)
```

Top and bottom flap rows above/below the body, separated from adjacent flaps
by slot cuts (the RSC defining feature).

## Material codes

| Code      | Description |
|-----------|-------------|
| sbs       | Solid bleached sulphate (white folding carton) |
| crb       | Coated recycled board |
| flute_b   | B-flute corrugated (3 mm) |
| flute_c   | C-flute corrugated (4 mm) |
| flute_bc  | BC double-wall (6 mm) |
| flute_e   | E-flute micro-flute (1.5 mm) |
| kraft     | Plain kraft / brown |
