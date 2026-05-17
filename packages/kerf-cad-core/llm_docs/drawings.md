# Drawings — Auto-Dimensioned Technical Drawing Generator

One-call generation of a fully annotated 4-view engineering drawing from a part description
dict, with DXF R12 and SVG 1.1 export.  Pure Python + NumPy.  Never raises.

---

## When to use

Keywords: auto dimension, technical drawing, engineering drawing, 2D drawing, DXF export,
SVG drawing, hole table, thread callout, fillet callout, GD&T annotation, title block,
front view, top view, section note, drawing sheet, A3 drawing, orthographic projection,
third-angle projection.

---

## Entrypoints

### `auto_dimension(part, view, sheet) -> dict`

Generate a 4-view (front / top / right / iso) technical drawing on the requested sheet.

**Parameters:**
- `part` — part description dict (schema below)
- `view` — reserved; always produces front/top/right/iso layout
- `sheet` — `"A3"` (default) | `"A0"` | `"A1"` | `"A2"` | `"A4"` | `"LETTER"`

**Part description schema:**
```json
{
  "name": "Bracket A",
  "material": "Steel 1045",
  "revision": "A",
  "drawn_by": "J. Smith",
  "project": "Widget Mk2",
  "bbox": { "length": 100.0, "width": 60.0, "height": 30.0 },
  "holes": [
    {
      "diameter_mm": 5.0,
      "depth_mm": 15.0,
      "x_mm": 20.0, "y_mm": 15.0, "z_mm": 30.0,
      "threaded": false,
      "thread_pitch_mm": null,
      "countersunk": false,
      "counterbored": false
    }
  ],
  "fillets": [
    { "radius_mm": 2.0, "count": 4, "face": "edge" }
  ],
  "internal_features": false,
  "mesh": null
}
```

**Returns:**
```json
{
  "ok": true,
  "views": {
    "front": { "visible": [...], "hidden": [...], "bbox": {...}, "label": "FRONT", "dimensions": [...] },
    "top":   { ... },
    "right": { ... },
    "iso":   { ... }
  },
  "annotations": {
    "overall_dims":    [...],
    "hole_table":      [...],
    "thread_callouts": [...],
    "fillet_callouts": [...],
    "section_note":    null,
    "gdt_frames":      [...],
    "title_block":     { "name": "...", "material": "...", "scale": "1:1", ... }
  },
  "sheet": {
    "size": "A3", "width_mm": 420.0, "height_mm": 297.0,
    "margin_mm": 10.0, "title_block_height_mm": 25.0,
    "border": [...], "title_block": [...]
  },
  "meta": { "drawing_id": "<uuid>", "scale": 1.0, "view_names": ["front","top","right","iso"] }
}
```

On error: `{"ok": false, "reason": "<msg>"}`.

---

### `dxf_export(drawing) -> str`

Serialize a Drawing dict to a DXF R12 string.  Returns `""` on invalid input.

Layers produced: `BORDER`, `VISIBLE`, `HIDDEN`, `DIM`, `ANNOT`, `HOLE_TABLE`,
`THREAD`, `FILLET`, `GDT`, `SECTION`, `TITLE`, `VIEWLABEL`.

---

### `svg_export(drawing) -> str`

Serialize a Drawing dict to an SVG 1.1 string.  Returns `""` on invalid input.

---

## Annotations generated automatically

| Annotation | Description |
|---|---|
| Overall L×W×H dims | Linear dimensions on front (L, H) and top (L, W) views |
| Hole table | Rows: `Ø<dia> ×<qty>` grouped by diameter; optionally `M<size>` |
| Thread callouts | One per unique threaded hole: `M<dia> ×<pitch> ×<depth> DP` |
| Fillet callouts | One per unique radius: `R<r>` on iso view |
| GD&T frames | Parallelism on dominant face; perpendicularity on right face; position on hole pattern |
| Section note | Added when `part.internal_features == true` |
| Title block | name, material, revision, drawn_by, project, sheet, scale |

---

## LLM tool names

| Tool | Function |
|---|---|
| `auto_dimension_generate` | Generate drawing dict from part description |
| `auto_dimension_export_dxf` | Export drawing dict → DXF R12 text |
| `auto_dimension_export_svg` | Export drawing dict → SVG 1.1 text |

---

## Usage snippets

```python
from kerf_cad_core.drawings.auto_dimension import auto_dimension, dxf_export, svg_export

part = {
    "name": "Cover Plate",
    "material": "Al 6061-T6",
    "bbox": {"length": 150, "width": 80, "height": 10},
    "holes": [
        {"diameter_mm": 6.5, "depth_mm": None, "x_mm": 20, "y_mm": 20,
         "z_mm": 10, "threaded": False, "thread_pitch_mm": None,
         "countersunk": False, "counterbored": False}
    ],
    "fillets": [{"radius_mm": 3.0, "count": 4, "face": "edge"}],
    "internal_features": False,
}
drawing = auto_dimension(part, sheet="A3")
dxf_text = dxf_export(drawing)
svg_text = svg_export(drawing)
```

```python
# Threaded-hole callout example
part["holes"].append({
    "diameter_mm": 5.0, "depth_mm": 12.0,
    "x_mm": 75, "y_mm": 40, "z_mm": 10,
    "threaded": True, "thread_pitch_mm": 0.8,
    "countersunk": False, "counterbored": False,
})
drawing = auto_dimension(part)
# annotations["thread_callouts"][0]["label"] == "M5 ×0.8 ×12 DP"
```

---

## Caveats

- View projection uses `kerf_cad_core.geom.make2d` when available; falls back to empty
  polylines when OCC is absent.  Annotations and structure are always generated.
- Auto-scale snaps to standard scales (1:20, 1:10, 1:5, 1:2, 1:1, 2:1, 5:1, 10:1).
- GD&T tolerances are nominal defaults (0.05 mm parallelism / perpendicularity,
  Ø0.10 position); override by editing the returned `gdt_frames` list before exporting.
- Third-angle projection only (ISO/ASME practice).

---

## References

ASME Y14.5-2018 Dimensioning and Tolerancing.

ISO 128-20:1996 Technical drawings — General principles of presentation.
