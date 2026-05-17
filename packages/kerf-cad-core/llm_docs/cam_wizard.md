# CAM Wizard — Stock Setup and Fixture Advisor

Pure-Python CNC setup wizard: stock selection, part orientation, fixture/clamping
recommendation, and machinist setup sheet.  No OCC dependency.  Never raises.

---

## When to use

Keywords: stock selection, CNC setup, machining setup, stock size, round bar, rectangular
bar, plate stock, surplus material, setup sheet, part orientation, fixture, clamping,
machinist vise, 3-jaw chuck, soft jaws, vacuum fixture, magnetic chuck, fixture tabs,
fixture plate, clamp position, avoid zone, zero point, material waste.

---

## Entrypoints

### `recommend_stock(part_aabb, material, surplus_mm) -> dict`

Select the closest standard stock size for a part.

**Parameters:**
- `part_aabb` — `{"min_x", "max_x", "min_y", "max_y", "min_z", "max_z"}` in mm
- `material` — material name or family keyword: `"aluminum"`, `"steel"`, `"stainless"`,
  `"brass"`, `"copper"`, `"titanium"`, `"magnesium"`, `"cast_iron"`, `"nylon"`,
  `"plastic"`, `"wood"`.  Also accepts exact matsel DB keys (e.g. `"Al_6061_T6"`).
- `surplus_mm` — extra material on each face (default `2.0` mm)

**Returns:**
```json
{
  "ok": true,
  "stock_type": "rect_bar|round_bar|plate",
  "dimensions_mm": { "width": 50, "height": 30, "length": 1000 },
  "part_dims_mm": { "L": 45, "W": 28, "H": 15 },
  "waste_pct": 72.4,
  "cost_estimate": {
    "currency": "USD",
    "amount": 4.20,
    "basis": "density × stock_volume × price_per_kg",
    "density_kg_m3": 2700.0,
    "stock_mass_kg": 1.68,
    "price_per_kg": 2.50
  },
  "material_used": "aluminum",
  "warnings": []
}
```

Stock series: EN 10058/10060 preferred widths (rectangular/plate) and diameters (round bar).
Standard lengths: 250, 500, 1000, 2000, 3000 mm.

---

### `recommend_orientation(part_geometry_summary) -> dict`

Choose the best part orientation to minimise Z-machining depth, limit overhangs, and
reduce re-fixturing.

**Parameters:**
- `part_geometry_summary` — dict with optional keys:
  - `aabb` — same schema as `recommend_stock`
  - `features` — list of feature keywords: `"pocket"`, `"through_hole"`, `"boss"`,
    `"slot"`, `"back_face"`, `"thread"`, etc.  `"through_hole"` and `"back_face"` imply
    second-op flip needed.
  - `notes` — free-text (passed through)

**Returns:**
```json
{
  "ok": true,
  "best_orientation": {
    "name": "flat_XY",
    "quaternion": [1.0, 0.0, 0.0, 0.0],
    "description": "Widest face sits on machine table (Z = part height)"
  },
  "score": 0.823,
  "all_candidates": [...],
  "rationale": "Orientation 'flat_XY' selected (score 0.823). ...",
  "warnings": []
}
```

Six candidate orientations (all 6 face-down positions).  Scoring: 40% Z-depth, 30%
base-face area, 30% re-fixturing penalty.

---

### `fixture_suggestion(orientation, stock_size, features_to_machine) -> dict`

Recommend clamping method and clamp positions.

**Parameters:**
- `orientation` — output from `recommend_orientation` (or `{"name": "flat_XY"}`)
- `stock_size` — output from `recommend_stock` (or `{"stock_type": ..., "dimensions_mm": ..., "material_used": ...}`)
- `features_to_machine` — list of feature keywords (optional)

**Returns:**
```json
{
  "ok": true,
  "clamp_method": "vise|chuck|soft_jaw|vacuum|magnet|fixture_plate_tabs",
  "clamp_description": "Machinist vise (small-to-medium rectangular block)",
  "clamp_positions": ["Jaw 1: ...", "Jaw 2: ..."],
  "fixture_tabs": null,
  "avoid_zones": ["Top face (primary machined face)"],
  "warnings": []
}
```

Decision logic: thin ferrous plate → magnetic chuck; thin non-ferrous → vacuum; shaft-like
→ 3-jaw chuck or soft jaws; large flat with large features → fixture-plate-tabs; default →
machinist vise.

---

### `setup_sheet(stock, orientation, fixture) -> dict`

Produce a complete machinist setup sheet with ASCII diagram.

**Parameters:**
- `stock` — output from `recommend_stock`
- `orientation` — output from `recommend_orientation`
- `fixture` — output from `fixture_suggestion`

**Returns:** title, stock_summary, orientation_note, zero_point, clamping_note,
clamp_positions, avoid_zones, fixture_tabs, text_diagram (ASCII art), cost_note.

---

## LLM tool names

| Tool | Function |
|---|---|
| `cam_recommend_stock` | Stock size + cost estimate |
| `cam_recommend_orientation` | Best orientation + scores |
| `cam_fixture_suggestion` | Clamp method + positions |
| `cam_setup_sheet` | Complete setup sheet |

---

## Usage snippets

```python
from kerf_cad_core.cam_wizard.stock_setup import recommend_stock, recommend_orientation, fixture_suggestion, setup_sheet

aabb = {"min_x": 0, "max_x": 80, "min_y": 0, "max_y": 40, "min_z": 0, "max_z": 20}
stock  = recommend_stock(aabb, "aluminum", surplus_mm=2.0)
# stock["stock_type"] == "rect_bar"
# stock["dimensions_mm"] == {"width": 45, "height": 25, "length": 250}

ori    = recommend_orientation({"aabb": aabb, "features": ["pocket", "through_hole"]})
fix    = fixture_suggestion(ori, stock, ["pocket", "through_hole"])
sheet  = setup_sheet(stock, ori, fix)
print(sheet["text_diagram"])
```

```python
# Round bar / shaft case
aabb = {"min_x": 0, "max_x": 200, "min_y": 0, "max_y": 25, "min_z": 0, "max_z": 25}
stock = recommend_stock(aabb, "steel")
# stock["stock_type"] == "round_bar"
# stock["dimensions_mm"]["diameter"] == 30  (next standard above ~35.4 = sqrt(25²+25²))
```

---

## References

EN 10058:2003 Hot-rolled flat steel bars.
EN 10060:2003 Hot-rolled round steel bars.
Machinery's Handbook, 30th ed. — Stock and material procurement.
