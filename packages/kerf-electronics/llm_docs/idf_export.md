# export_idf — IDF 3.0 ECAD↔MCAD board exchange

## Purpose

Exports a CircuitJSON PCB board as an **IDF 3.0** ECAD↔MCAD exchange package — the standard handoff format between electronic CAD (ECAD) tools like KiCad/Altium and mechanical CAD (MCAD) tools like SolidWorks, CATIA, PTC Creo and Autodesk Inventor.

Returns two files:
| File | Content |
|------|---------|
| `<stem>.emn` | Board file — outline, drilled holes, component placement |
| `<stem>.emp` | Library file — component outlines and body heights |

## When to use

- Mechanical team needs board dimensions and component keep-outs for enclosure design
- Fit-check or collision detection without needing a full 3D solid
- DFM review of component heights and placement clearances
- Importing PCB into SolidWorks/Creo/Inventor via their IDF import wizard

For a full 3D STEP solid (substrate + component bodies) use `export_board_step` instead.

## IDF 3.0 sections emitted

### .emn board file

| Section | Content |
|---------|---------|
| `.HEADER` | `BOARD_FILE 3.0`, board name, timestamp, `MM` units |
| `.BOARD_OUTLINE` | Edge-cuts polygon (loop 0), board thickness, arc angle = 0.0 for straight segments |
| `.DRILLED_HOLES` | Via, PTH pad and mounting-hole coordinates + diameters (`PTH BOARD NOPIN VIA`) |
| `.PLACEMENT` | Per component: refdes, package, x, y, z, rotation (deg), `TOP`/`BOTTOM` side |

### .emp library file

| Section | Content |
|---------|---------|
| `.HEADER` | `LIBRARY_FILE 3.0`, board name, timestamp |
| `.ELECTRICAL` | One section per unique package — rectangular bounding-box outline + height (mm) |

## Geometry consistency

All geometry is extracted by the same helpers used by `export_board_step`:

- **Board outline** — `pcb_outline_path` polygon (priority) or `pcb_board` bounding rectangle
- **Drilled holes** — `pcb_via`, `pcb_plated_pad` (with `hole_diameter` > 0), `pcb_hole`, `pcb_mounting_hole`
- **Component placement** — `pcb_component` linked to `source_component` (refdes, footprint, side, rotation)
- **Package sizes** — `_estimate_body_size` heuristic from footprint name (R_0402, TQFP-32, SOIC-8, …); falls back to 2.5 × 2.5 × 1.5 mm for unknown footprints

This means the board outline, hole positions and component placement in the IDF files always match what `export_board_step` produces.

## Z placement convention

| Side | z_mm in .PLACEMENT |
|------|--------------------|
| Top  | `0.0` (flush with board surface) |
| Bottom | `-body_height_mm` (below board) |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `circuit_json` | array | required | Parsed CircuitJSON array |
| `stem` | string | `"board"` | Output filename stem → `<stem>.emn` + `<stem>.emp` |
| `board_thickness_mm` | number | `1.6` | PCB thickness in mm (0.8 / 1.0 / 1.2 / 1.6 / 2.0 common) |

## Return payload

```json
{
  "emn_filename": "board.emn",
  "emp_filename": "board.emp",
  "emn_b64": "<base64>",
  "emp_b64": "<base64>",
  "emn_size_bytes": 1234,
  "emp_size_bytes": 567,
  "placement_count": 12,
  "hole_count": 4,
  "package_count": 5,
  "message": "IDF 3.0 export complete: board.emn + board.emp. ..."
}
```

Decode `emn_b64` and `emp_b64` to obtain the raw file bytes for download.

## No extra dependencies

Pure Python — no pythonOCC, no shapely, no external tools. Always available.

## Workflow example

```
User: Export the board for SolidWorks hand-off

→ call export_idf({ circuit_json: [...], stem: "mcu_rev3", board_thickness_mm: 1.6 })
→ decode emn_b64 → save mcu_rev3.emn
→ decode emp_b64 → save mcu_rev3.emp
→ import both files into SolidWorks via File → Import → IDF
```
