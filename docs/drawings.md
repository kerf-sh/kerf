# Drawings

TechDraw-flavored 2D engineering drawings: multi-sheet, projected views,
dimensions, annotations, and engineering symbols.

## What a drawing is

A `.drawing` file is JSON describing one or more **sheets**. Every sheet owns a
frame (paper size, title block), a list of projected **views** of 3D source
files, plus dimensions, annotations, centerlines, break-lines, and engineering
symbols layered on top.

Coordinates throughout are **page millimetres** (top-left origin).

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

Add a sheet via the **+** tab or the `add_sheet` tool. Set sheet-level
properties via `set_drawing_scale` and `set_title_field`.

## View types

Every view projects a 3D source (`.jscad`, `.assembly`, or `.step`) onto a
plane. The view's `position` is page-mm of its bounding-box top-left.

| Projection                                       | Use                                  |
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

Section *cuts* — actually slicing the geometry along a section line — are
planned.

### Detail views

Planned: zoom-and-crop of a region of a parent view, with its own scale label.

## Dimensions

Dimensions read live from the projected geometry; an optional `value` string
overrides the auto-measurement (the UI flags overrides with a small "M" badge).

| Kind        | Description                                           |
|-------------|-------------------------------------------------------|
| `linear`    | Horizontal or vertical distance between two picks     |
| `aligned`   | Distance along the line connecting two picks          |
| `radius`    | Arc / circle radius                                   |
| `diameter`  | Circle diameter                                       |
| `angular`   | Angle between two picks at a vertex                   |
| `baseline`  | Multiple distances all measured from a single datum   |
| `chain`     | A run of consecutive distances between adjacent picks |
| `ordinate`  | Distances from an origin, drawn as labelled offsets   |

Add via:

- **Dimension toolbar** in the editor — click the kind, then pick the geometry.
- **LLM:** `add_dimension` — one polymorphic tool, dispatched on `kind`.

The `offset` field on linear/aligned/baseline/chain controls how far the
dimension line stands off from the geometry.

## Annotations

Free text and visual callouts — most carry an optional `view_id` to ride with
their view, or float free on the sheet.

| Kind             | Visual                                                |
|------------------|-------------------------------------------------------|
| `text`           | Plain text, freely placed                             |
| `note`           | Boxed text — for shop notes / general specs           |
| `leader`         | Arrow + text from a target point to a label position  |
| `balloon`        | Numbered circle for BOM callouts; optional leader     |
| `polyline` / `rect` / `circle` | Free-drawn vector shapes                |

Add via the annotation toolbar or `add_annotation` (polymorphic by `kind`),
remove via `remove_annotation`.

## Engineering symbols

| Symbol            | Params                                           |
|-------------------|--------------------------------------------------|
| `surface_finish`  | `ra` (roughness), `machined: bool`               |
| `weld`            | `text`, `side: 'arrow' \| 'other'`               |
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

## Wire format

Full schema in `CONTRACT.md` under "Drawing files".

Next: [cloud.md](./cloud.md)
