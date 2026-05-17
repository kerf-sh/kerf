# cam_wizard_stock_setup — CNC Stock-Setup Wizard

Stock selection, part orientation, fixture suggestion, and setup-sheet generation for CNC machining. Pure Python, never raises.

## When to use

Use these tools when a machinist or CAM engineer needs to:
- Find the closest standard stock size (rectangular bar/plate, round bar, or billet) for a part
- Determine the best part orientation in stock to minimise Z-depth, limit overhangs, and reduce re-fixturing
- Get a fixture / clamping suggestion (vise, chuck, soft-jaw, fixture-plate + tabs, vacuum, magnet)
- Generate a machinist setup-sheet with a text diagram, zero point, clamp positions, and orientation summary

Keywords: stock, stock selection, raw stock, CNC stock, rectangular bar, round bar, plate, billet, waste, waste percent, part orientation, fixturing, clamping, vise, soft jaw, fixture plate, fixture tabs, vacuum fixture, setup sheet, machining orientation, stock size.

## Standard stock tables

**Rectangular bar / plate — EN/ISO preferred widths (mm):**
6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 120, 150, 200, 250, 300

**Standard lengths:** 250, 500, 1000, 2000, 3000 mm

**Round bar diameters (mm):**
3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120, 150, 200, 250, 300

References: EN 10060:2003 (round bars), EN 10058:2003 (flat bars), Machinery's Handbook 30th ed.

## Material density fallbacks

When `matsel.db` is unavailable the wizard uses keyword-based density lookup:

| Keyword | Density (kg/m³) |
|---|---|
| aluminum / aluminium / al | 2700 |
| steel | 7850 |
| stainless | 8000 |
| brass | 8500 |
| copper | 8940 |
| titanium / ti | 4430 |
| plastic | 1200 |

## Tools

| Tool | Description |
|------|-------------|
| `stock_recommend` | Read-only: return closest standard rectangular bar/plate or round bar to fit the part AABB; inputs: `part_aabb` `{x, y, z}` (mm), `material` string, `surplus_mm` (extra clearance, default 5 mm); returns: `stock_type`, `dimensions`, `waste_pct`, `cost_estimate_usd` |
| `orientation_recommend` | Read-only: choose best part orientation to minimise total Z-depth of machining, limit overhangs, reduce re-fixturing; inputs: `part_geometry_summary` dict; returns: `rotation_quaternion` `[w,x,y,z]`, `score`, `rationale` |
| `fixture_suggest` | Read-only: suggest clamping method and positions; inputs: `orientation` (from `orientation_recommend`), `stock_size` dict, `features_to_machine` list; returns: `clamping_method`, `clamp_positions`, `tab_count` (if applicable), `notes` |
| `setup_sheet_generate` | Read-only: produce a complete setup-sheet dict; inputs: `stock` (from `stock_recommend`), `orientation` (from `orientation_recommend`), `fixture` (from `fixture_suggest`); returns: `text_diagram`, `zero_point`, `clamping_arrangement`, `operations_sequence` |

### `stock_recommend` key outputs

- `stock_type` — `rectangular_bar` | `round_bar`
- `dimensions` — `{width_mm, height_mm, length_mm}` for rectangular; `{diameter_mm, length_mm}` for round
- `waste_pct` — (stock_volume − part_volume) / stock_volume × 100
- `cost_estimate_usd` — density × volume × cost_per_kg_usd (material-dependent)

### `fixture_suggest` clamping methods

| Method | When used |
|---|---|
| `vise` | Default for rectangular stock < 300 mm |
| `chuck` | Round bar; cylindrical parts |
| `soft_jaw` | Curved or irregular part profiles |
| `fixture_plate_tabs` | Thin plate parts; tabs hold part in blank until last op |
| `vacuum` | Thin sheet; flat parts; non-magnetic |
| `magnet` | Ferrous parts on a magnetic chuck |

## Example

Machinist: "I need to machine an aluminium part 85 × 40 × 28 mm. What stock and fixture do I need?"

1. `stock_recommend` — part_aabb={x:85,y:40,z:28}, material=`aluminium`, surplus_mm=5 → rectangular_bar 90×45 mm from stock, length 90 mm, waste_pct=32%
2. `orientation_recommend` — part_geometry_summary={bbox_x:85,bbox_y:40,bbox_z:28,...} → rotation to minimise Z-depth; score=0.87
3. `fixture_suggest` — orientation=`<from step 2>`, stock_size={width_mm:90,height_mm:45,length_mm:90}, features_to_machine=["top_face","holes"] → vise, clamp positions at ±20 mm from centre
4. `setup_sheet_generate` → text diagram + zero-point at bottom-left-front corner + ops sequence
