# drawings_auto_dimension — One-Button Auto-Dimensioned Engineering Drawing

Generates a fully dimensioned technical drawing from a part description dict: 4-view sheet, L × W × H dimensions, hole table, thread callouts, fillet radius callouts, GD&T frames, and DXF / SVG export.

## When to use

Use these tools when an engineer or designer needs to:
- Automatically dimension a machined part in a standard multi-view technical drawing
- Generate a hole table with X/Y centres, diameters, and quantities
- Add thread callouts (M<size> × <pitch> × <depth> DP) for threaded features
- Include fillet R-callouts and sectional view notes for internal features
- Apply GD&T frames: parallelism / perpendicularity on largest faces, position tolerance on critical hole patterns
- Export the drawing to DXF R12 or SVG 1.1

Keywords: auto dimension, technical drawing, engineering drawing, multi-view, 4-view, third-angle projection, hole table, thread callout, fillet callout, GD&T frame, A3 sheet, DXF export, SVG export, title block, sectional view, perpendicularity, parallelism, position tolerance.

## Sheet defaults

- A3 landscape with 1:1 or auto-scaled to fit
- Views: front, top, right, iso (isometric) in third-angle projection
- Title block with project / revision / drawn-by / material metadata

## Part description schema

```
{
  "name":     str,              // e.g. "Bracket A"
  "material": str | None,
  "revision": str | None,       // e.g. "A"
  "drawn_by": str | None,
  "project":  str | None,
  "bbox": {                     // overall bounding box (mm)
    "length": float,            // X extent
    "width":  float,            // Y extent
    "height": float,            // Z extent
  } | None,
  "holes": [
    {
      "diameter_mm":  float,
      "depth_mm":     float | None,
      "x_mm":         float,
      "y_mm":         float,
      "z_mm":         float,
      "threaded":     bool,
      "thread_pitch_mm": float | None,
      "countersunk":  bool,
      "counterbored": bool,
    }
  ],
  "fillets": [
    {
      "radius_mm": float,
      "count":     int,
      "face":      str | None,  // "top" | "bottom" | "edge"
    }
  ],
  "internal_features": bool,    // true → add sectional view note
  "mesh": {                     // optional; used by Make2D for accurate projections
    "vertices":  [[x,y,z], ...],
    "triangles": [[i,j,k], ...],
  } | None,
}
```

## Drawing output keys

```
{
  "views":       [{ "name": str, "polylines": [...], "dimensions": [...] }],
  "hole_table":  [{ "label": str, "x": float, "y": float, "diameter": float, "qty": int }],
  "annotations": [{ "type": "thread"|"fillet"|"gdt"|"section_note", "text": str, ... }],
  "sheet":       { "width_mm": 420, "height_mm": 297, "title_block": {...} },
  "meta":        { "scale": float, "units": "mm", "projection": "third_angle" }
}
```

## GD&T frames auto-placed

- Parallelism / perpendicularity callouts on the largest planar faces
- Position tolerance on the most-critical hole pattern (pattern with most holes or smallest hole)
- Tolerance values derived from ISO 286-1 IT7 grade (default)

## Tools

| Tool | Description |
|------|-------------|
| `auto_dimension_generate` | Read-only: generate a Drawing dict from a part description; required: `part` dict; optional `view` (default `front_top_right_iso`), `sheet` (`A3` or `A4`) |
| `auto_dimension_export_dxf` | Read-only: serialise a Drawing dict to DXF R12 text string; required: `drawing` |
| `auto_dimension_export_svg` | Read-only: serialise a Drawing dict to SVG 1.1 text string; required: `drawing` |

## Example

Engineer: "Generate a dimensioned drawing for an aluminium bracket 100 × 50 × 30 mm with two M6 holes and four 2 mm fillets. Export as DXF."

1. `auto_dimension_generate` — part={name:"Bracket A", material:"Aluminium 6082", bbox:{length:100,width:50,height:30}, holes:[{diameter_mm:6,x_mm:20,y_mm:25,z_mm:30,threaded:true,thread_pitch_mm:1.0},{diameter_mm:6,x_mm:80,y_mm:25,z_mm:30,threaded:true,thread_pitch_mm:1.0}], fillets:[{radius_mm:2,count:4}]}
2. `auto_dimension_export_dxf` — drawing=`<from step 1>` → DXF R12 text string
