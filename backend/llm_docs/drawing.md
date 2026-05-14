# Authoring `.drawing` files

A `.drawing` is a JSON document holding one or more sheets. Each sheet
has a frame (paper size, title block), one or more projected views of
3D source files, dimensions, annotations, centerlines, breaks, and
engineering symbols. The frontend renders the SVG live from the JSON.

Coordinates are in **page millimetres** (so a 420mm-wide A3 sheet has
its right edge at x=420). The Y axis points DOWN in page space.

Create a drawing with `create_file(path, kind='drawing')` and an empty
seed `{}` content; the frontend will hydrate defaults on load. Or
write your own seed via `write_file`.

## Top-level shape (canonical, multi-sheet)

```json
{
  "sheets": [
    {
      "id": "sh-1",
      "frame": {
        "size": "A3",
        "orientation": "landscape",
        "title": "Bracket — Assembly",
        "scale_label": "1:1",
        "sheet_number": "1/1",
        "template": "default",
        "author": "...",
        "date": "2026-...",
        "notes": "...",
        "extra": {}
      },
      "views":       [ ... ],
      "dimensions":  [ ... ],
      "annotations": [ ... ],
      "centerlines": [ ... ],
      "breaks":      [ ... ],
      "symbols":     [ ... ]
    }
  ]
}
```

The legacy single-sheet shape (top-level `frame` / `views` / …) still
loads, but always WRITE the `sheets[]` form for new content.

### Frame

- `size` — `A4|A3|A2|A1|A0|ANSI_A|ANSI_B|ANSI_C|ANSI_D`.
- `orientation` — `landscape|portrait`.
- `template` — `default|iso|ansi|kerf` (frontend renders the title
  block accordingly).
- `extra` — free-form key→string for template-specific fields like
  `material`, `tolerances`, `revision`.

## Views

Each view projects ONE 3D source file (`.jscad`, `.feature`, `.step`,
or `.assembly`) onto the page.

```json
{
  "id": "v-front",
  "source_file_id": "<uuid>",
  "part_id": "*",                  // "*" or omitted = all Objects
  "projection": "front",           // front|top|right|left|back|bottom|iso
  "scale": 1.0,                    // model units per page mm
  "position": [40, 100],           // [x_mm, y_mm] top-left of bbox
  "show_hidden": true,
  "show_silhouette": true,
  "label": "F",
  "is_section": false,             // true → render hatched section
  "hatch_spacing": 2.5,
  "hatch_angle": 45
}
```

A 3-view first-angle layout (Front, Top, Right) is conventional for
machined parts: Front in the middle, Top above Front, Right to the
right of Front.

## Dimensions

Dimensions are typed by `kind`. ALL coordinates here are in page mm
(post-projection), not model units. Pass `value` (string) to override
the auto-measured label.

```json
{
  "id": "d-1",
  "view_id": "v-front",
  "kind": "linear",
  "a": {"x": 40, "y": 80},
  "b": {"x": 90, "y": 80},
  "offset": 8,
  "value": null            // optional manual override string
}
```

Required fields by kind:

| `kind`     | Required                        | Optional        |
|------------|---------------------------------|-----------------|
| `linear`   | `a`, `b`, `offset`              | `value`         |
| `aligned`  | `a`, `b`, `offset`              | `value`         |
| `radius`   | `a`, `b`, `offset`              | `value`         |
| `diameter` | `a`, `b`, `offset`              | `value`         |
| `angular`  | `vertex`, `a`, `b`, `radius`    | `value`         |
| `baseline` | `picks: [{x,y},…]`, `offset`    | `value`         |
| `chain`    | `picks: [{x,y},…]`, `offset`    | `value`         |
| `ordinate` | `picks: [{x,y},…]`, `origin`    | `value`         |

Picker rules of thumb:
- Distances → `linear` (axis-aligned) or `aligned` (along the line).
- Circles → `radius` for arcs, `diameter` for full circles
  (rendered with `R` / `Ø` prefixes).
- Angles → `angular` at a vertex with `radius` controlling the dim arc.
- Rows of holes → `baseline` (all from one datum) or `chain`
  (consecutive distances).
- X / Y from origin per pick → `ordinate`.

## Annotations

Polymorphic on `kind`:

`text` `note` `leader` `balloon` `polyline` `rect` `circle`
`surface_finish` `weld` `gdt`

Common shapes:

```json
{ "id": "a-1", "kind": "text",
  "view_id": "v-front", "x": 50, "y": 200,
  "text": "Note: deburr all edges", "fontSize": 3 }

{ "id": "a-2", "kind": "leader",
  "from": {"x": 80, "y": 90}, "to": {"x": 60, "y": 110},
  "text": "Ø3 thru" }

{ "id": "a-3", "kind": "balloon",
  "x": 60, "y": 80, "leader": {"x": 80, "y": 90},
  "number": "3" }

{ "id": "a-4", "kind": "polyline",
  "points": [{"x":40,"y":40},{"x":80,"y":40},{"x":80,"y":80}],
  "stroke": "#000", "dashed": false }

{ "id": "a-5", "kind": "rect",
  "x": 350, "y": 270, "width": 60, "height": 20,
  "stroke": "#000", "fill": "none" }

{ "id": "a-6", "kind": "circle",
  "cx": 100, "cy": 100, "r": 5 }
```

### GD&T frame

```json
{
  "id": "g-1", "kind": "gdt",
  "x": 120, "y": 90,
  "params": {
    "symbol": "⌖",        // position. Other syms: ⏥ ∥ ⊥ ∠ ⌭ ⌒
    "tolerance": "0.05",
    "modifier": "Ⓜ",     // M/L/P or omit
    "datums": ["A", "B", "C"]
  }
}
```

### Surface finish

```json
{ "id": "g-2", "kind": "surface_finish",
  "x": 80, "y": 90,
  "params": { "ra": "1.6", "type": "machined" } }
```

### Weld

```json
{ "id": "g-3", "kind": "weld",
  "from": {"x": 60, "y": 90}, "to": {"x": 100, "y": 90},
  "params": { "process": "fillet", "size": 5 } }
```

## Centerlines

```json
{ "id": "cl-1", "view_id": "v-front",
  "style": "center_dashed",
  "refs": ["edge-h-1"]                 // auto-detect via edge id
}

{ "id": "cl-2", "view_id": "v-front",
  "custom": { "p1": {"x":40,"y":80}, "p2": {"x":120,"y":80} } }
```

## Breaks

Visual zigzag plus a flag on the view describing which range is
collapsed.

```json
{ "id": "br-1", "view_id": "v-side",
  "orientation": "horizontal",
  "p1": {"x": 200, "y": 100}, "p2": {"x": 220, "y": 100},
  "style": "zigzag" }
```

## Multi-sheet drawings

Append a sheet to `sheets[]`. Sheets render independently; views can
reference any source file. To link a view across sheets you'd duplicate
its definition — there's no cross-sheet view inheritance.

## Common edits

### New A3 landscape drawing with a Front view of `/main.jscad`

`create_file('/main.drawing', kind='drawing', content='{}')` — frontend
hydrates defaults on next load.

To pre-seed:

```json
{
  "sheets": [{
    "id": "sh-1",
    "frame": {"size":"A3","orientation":"landscape","title":"Main"},
    "views": [
      {"id":"v-front","source_file_id":"<uuid>","part_id":"*",
       "projection":"front","scale":1,"position":[40,80],
       "show_hidden":true,"show_silhouette":true,"label":"F"}
    ],
    "dimensions": [], "annotations": [],
    "centerlines": [], "breaks": [], "symbols": []
  }]
}
```

### Add a 3-view layout to an existing drawing

Compute three view entries with positions `(40,160)`, `(40,80)`,
`(160,160)` (Front, Top, Right; first-angle) and append them all to
`sheets[0].views`. Each shares the same `source_file_id` and `scale`.

### Remove a view + its dimensions

Strip the view from `sheets[i].views`, then strip every dimension from
`sheets[i].dimensions` whose `view_id` matches. Same for centerlines
and breaks.
