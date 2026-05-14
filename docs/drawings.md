# Drawings

TechDraw-flavored 2D engineering drawings: multi-sheet, projected views,
dimensions, annotations, and engineering symbols.

## What a drawing is

A `.drawing` file is JSON describing one or more **sheets**. Every sheet owns a
frame (paper size, title block), a list of projected **views** of 3D source
files, plus dimensions, annotations, centerlines, break-lines, and engineering
symbols layered on top.

Coordinates throughout are **page millimetres** (top-left origin).

## Drawings vs Sheets vs Views

| Artifact         | What it is                                                           | When to use                                |
|------------------|---------------------------------------------------------------------|--------------------------------------------|
| `.drawing`       | The root document — one or more sheets, full drawing state           | Every drawing starts here                  |
| `.view.json`     | A saved camera/projection from a `.bim` model (Revit-style)         | Reuse a specific view across drawings      |
| `.sheet.json`    | A print-ready layout: title block + positioned viewports            | Pre-built sheet templates for reuse        |

A `.view.json` captures `source_file_id`, `projection`, `scale`, `position`,
and camera pose — drop it onto any sheet to restore that exact viewport.
A `.sheet.json` holds a populated `frame` plus an array of viewport slots,
each referencing a `.view.json`. Assemble sheets from views for complex
multi-view layouts.

## Create a drawing

File tree → **New file → Drawing**. The Drawing Editor opens with a single
default sheet (A4 landscape, ISO template).

<!-- screenshot: blank drawing sheet -->

From chat, the `create_drawing` tool seeds a drawing with a chosen source file
and a 3-view layout:

> *"Create a drawing of bracket.jscad with front, top, and right views."*

## Sheets

A sheet is a paper. Multi-sheet drawings keep an array of them; the editor
shows a tab strip across the bottom.

```ts
{
  id, frame: { size, orientation, template, title, author, ... },
  views, dimensions, annotations, centerlines, breaks, symbols
}
```

Sheet sizes: `A4` / `A3` / `A2` / `A1` / `A0` / `ANSI_A` / `ANSI_B` / `ANSI_C`
/ `ANSI_D`. Templates: `default`, `iso`, `ansi`, `kerf`. Each template
supplies a different title-block layout and exposes its own extra fields
(material, tolerances, revision) under `frame.extra`.

Add a sheet via the **+** tab or `add_sheet`. Set sheet-level properties via
`set_drawing_scale` and `set_title_field`.

### Sheets + Revisions

Revisions auto-number upward: `A → B → … Z → AA → AB → … ZZ`. Use
`add_sheet_revision` to stamp a new rev on a sheet's frame. `update_title_block_field`
writes any frame field (`title`, `author`, `date`, `scale_label`, `sheet_number`,
`notes`, or any `extra` key):

```
update_title_block_field(sheet_id, field="revision", value="B")
update_title_block_field(sheet_id, field="extra.material", value="6061-T6")
```

## View types

Every view projects a 3D source (`.jscad`, `.assembly`, `.step`) onto a plane.
The view's `position` is page-mm of its bounding-box top-left.

| Projection                                         | Use                                  |
|--------------------------------------------------|--------------------------------------|
| `front` / `top` / `right` / `left` / `back` / `bottom` | Standard orthographic              |
| `iso`                                            | Isometric for orientation reference  |

Add views via:

- **Toolbar → Add view** — pick projection, click to place.
- **Toolbar → Standard views** — drops a 3-view (front/top/right) or 6-view
  layout in first-angle convention.
- LLM: `add_view_to_drawing`, `add_standard_views`.

### Section views

Set `is_section: true` on a view. The renderer fills the projected bbox with a
45° SVG `<pattern>` hatch clipped to the section's bounded region. `hatch_spacing`
and `hatch_angle` are tunable per-view.

### Hatching

`add_hatch_to_drawing` fills a closed boundary with a crosshatch pattern.

```ts
add_hatch_to_drawing({
  sheet_id, boundary: { kind:"polyline"|"circle"|"rect", ... },
  pattern: "ANSI31" | "ANSI32" | "ANSI33" | "ANSI34" | "ANSI35" |
           "ARB025" | "BRICK" | "CELTIC" | "DOTS" | "EARTH" |
           "FLEX" | "GOST_ACK" | "GOST_CARDBOARD" | "GOST_CONCRETE" |
           "GOST_CORK" | "GOST_CROSS" | "GOST_DIAMOND" | "GOST_GLOBAL" |
           "GOST_INSUL" | "GOST_METAL" | "GOST_PLASTIC" | "GOST_STONE" |
           "GOST_TILE" | "HONEYCOMB" | "ISO02" | "ISO03" | "ISO04" |
           "ISO05" | "ISO06" | "ISO07" | "ISO10" | "ISO11" | "ISO12" |
           "PLASTIC" | "SQUARES" | "STEEL" | "SWAMP" | "Zebra",
  scale: 1.0, angle: 45
})
```

For custom patterns, drop a `.pat` seed file under `seed/hatch_library/`
and reference it by name. Full pattern spec: `packages/kerf-chat/llm_docs/drawing.md`.

### Detail views

Planned: zoom-and-crop of a region of a parent view, with its own scale label.

## Dimensions

Dimensions read live from the projected geometry; an optional `value` string
overrides the auto-measurement (the UI flags overrides with a small "M" badge).

| Kind          | Description                                           |
|---------------|-------------------------------------------------------|
| `linear`      | Horizontal or vertical distance between two picks     |
| `aligned`     | Distance along the line connecting two picks          |
| `radius`      | Arc / circle radius                                   |
| `diameter`    | Circle diameter                                       |
| `angular`     | Angle between two picks at a vertex                   |
| `baseline`    | Multiple distances all measured from a single datum    |
| `chain`       | A run of consecutive distances between adjacent picks |
| `ordinate`    | Distances from an origin, drawn as labelled offsets   |

Add via:

- **Dimension toolbar** in the editor — click the kind, then pick the geometry.
- **LLM:** `add_dimension` — one polymorphic tool, dispatched on `kind`.

The `offset` field on linear/aligned/baseline/chain controls how far the
dimension line stands off from the geometry.

### Dimension chains

`add_dimension_chain_to_drawing` places a full chain in one call — picks are
laid end-to-end and each segment gets its own label. Returns all the created
dimension IDs:

```
add_dimension_chain_to_drawing({ sheet_id, view_id, picks:[{x,y},...], offset:8 })
```

## Annotations

Free text and visual callouts — most carry an optional `view_id` to ride with
their view, or float free on the sheet.

| Kind                      | Visual                                              |
|---------------------------|-----------------------------------------------------|
| `text`                    | Plain text, freely placed                           |
| `note`                    | Boxed text — for shop notes / general specs         |
| `leader`                  | Arrow + text from a target point to a label position |
| `rich_text`              | Multi-line / bold / italic annotation              |
| `balloon`                 | Numbered circle for BOM callouts; optional leader   |
| `polyline` / `rect` / `circle` | Free-drawn vector shapes                           |

### Leader lines

`add_leader_to_drawing` draws an arrow from a pick point to a text anchor:

```
add_leader_to_drawing({ sheet_id, from:{x,y}, to:{x,y}, text:"Ø3 thru" })
```

### Rich text

`add_rich_text_to_drawing` places formatted text blocks with line breaks and
font styling:

```
add_rich_text_to_drawing({ sheet_id, x:50, y:200, lines:[
  { text:"MATERIAL:", bold:true },
  { text:"6061-T6 Aluminum", bold:false }
]})
```

Add via the annotation toolbar or `add_annotation` (polymorphic by `kind`),
remove via `remove_annotation`.

## Engineering symbols

| Symbol            | Params                                           |
|-------------------|--------------------------------------------------|
| `surface_finish`  | `ra` (roughness), `machined: bool`               |
| `weld`            | `text`, `side: 'arrow' \| 'other'`              |
| `gdt`             | `characteristic`, `tolerance`, `datums[]`        |

GD&T frames render as multi-cell tables per ASME Y14.5. Add via
`add_annotation` with `kind: 'gdt'`.

## Centerlines and break-lines

`add_centerline` — pass `refs: edge_ids` to auto-detect (e.g. through a hole's
two arc edges) or `custom: { p1, p2 }` to place manually.

`add_break` — defines a visual elision between two points, drawn as a zigzag.
`orientation` is `'horizontal' | 'vertical'`.

## Multi-sheet workflow

A typical engineering drawing fans out across multiple sheets:

1. **Sheet 1** — assembly view + BOM balloons.
2. **Sheet 2** — exploded view + sectioned details.
3. **Sheet 3+** — per-part detail sheets.

Use `add_sheet` to append, then `add_view_to_drawing` / `add_standard_views`
into each sheet. The serializer keeps a top-level mirror of `sheets[0]` for
back-compat with the original single-sheet format; readers prefer
`sheets[]` when present.

## Title block

Every sheet's frame has canonical fields (`title`, `author`, `date`,
`scale_label`, `sheet_number`, `notes`) plus a template-specific `extra` map.
Set them with `set_title_field`. The active template decides which fields
actually show — the rest stay in JSON.

## PDF / SVG export

The export button on the editor toolbar produces:

- **PDF** — one page per sheet via `jspdf` + `svg2pdf.js`.
- **SVG** — one file per sheet, raw vector for handing off to a layout tool.

## DXF export

Via the `.draft` file kind's `export_draft_dxf` tool. Draft files share the
same projection/annotation model as drawings; export any sheet or view to DXF
for CAM or third-party CAD.

## Wire format

Full schema in `packages/kerf-chat/llm_docs/drawing.md`.

Next: [cloud.md](./cloud.md)
