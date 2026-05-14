# Sheet (.sheet.json) — Print-ready layouts

A **sheet** is a print-ready composition: a paper size, title block, and one or
more viewports that each reference a `.view.json` file. Sheets live as files
with `kind = 'sheet'` in the project tree.

---

## Schema

```jsonc
{
  "version": 1,
  "id": "uuid",
  "name": "A-101 Floor Plans",
  "sheet_number": "A-101",
  "size": "A1",               // A0..A4 | ANSI_A..ANSI_E
  "orientation": "landscape", // landscape | portrait
  "titleblock": {
    "project_name": "Office Tower",
    "issue_date": "2026-05-14",
    "revision": "A",
    "drawn_by": "Jane Smith"
  },
  "viewports": [
    {
      "id": "vp-uuid",
      "view_file_id": "view-uuid",
      "position": [50, 80],   // mm from sheet origin (bottom-left)
      "scale": 0.02,           // 0.02 = 1:50
      "title": "Level 1"
    }
  ],
  "revision_clouds": [
    {
      "id": "rc-uuid",
      "polygon": [[100,200],[200,200],[200,300],[100,300]],
      "revision": "A",
      "note": "wall thickness updated"
    }
  ]
}
```

### Paper sizes (mm, portrait base)

| Size   | Width | Height |
|--------|------:|-------:|
| A0     |   841 |   1189 |
| A1     |   594 |    841 |
| A2     |   420 |    594 |
| A3     |   297 |    420 |
| A4     |   210 |    297 |
| ANSI_A |   216 |    279 |
| ANSI_B |   279 |    432 |
| ANSI_C |   432 |    559 |
| ANSI_D |   559 |    864 |
| ANSI_E |   864 |   1118 |

### Scale convention

`scale` is the ratio of drawing units to real units.  
`0.02` = 1:50, `0.01` = 1:100, `0.05` = 1:20.

---

## Tools

| Tool | Description |
|------|-------------|
| `create_sheet` | Create a new `.sheet.json` file |
| `add_viewport_to_sheet` | Add a viewport referencing a view |
| `remove_viewport` | Remove a viewport by id |
| `add_revision_cloud` | Mark a revision area with a cloud polygon |

---

## Examples

### 1 — Create an A1 landscape sheet

```json
{
  "tool": "create_sheet",
  "args": {
    "path": "/Office Tower/Sheets/A-101.sheet.json",
    "name": "A-101 Floor Plans",
    "sheet_number": "A-101",
    "size": "A1",
    "orientation": "landscape"
  }
}
```

### 2 — Place a floor-plan view at 1:50

```json
{
  "tool": "add_viewport_to_sheet",
  "args": {
    "sheet_file_id": "sheet-file-uuid",
    "view_file_id":  "view-file-uuid",
    "position": [50, 80],
    "scale": 0.02,
    "title": "Level 1 Floor Plan"
  }
}
```

### 3 — Mark a revision area

```json
{
  "tool": "add_revision_cloud",
  "args": {
    "sheet_file_id": "sheet-file-uuid",
    "polygon": [[100,200],[250,200],[250,350],[100,350]],
    "revision": "B",
    "note": "structural column relocated"
  }
}
```
