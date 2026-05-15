# Architectural BIM Primitives

Pure-Python parametric model layer for walls, doors, windows, slabs, and
openings.  No 3D geometry is produced here — each tool returns a self-contained
**parametric recipe** that downstream workers use to construct geometry.

**All dimensions are in millimetres throughout.**

Returns `{ok: false, errors: [...]}` on bad input.  Never raises.

---

## Tools

### `arch_wall`

Create a parametric wall from a baseline and height.

**Input:**
- `start` (required) — baseline start `[x, y]` in mm (plan view)
- `end` (required) — baseline end `[x, y]` in mm
- `height` (required) — wall height in mm (> 0)
- `thickness` — total thickness in mm (required unless `layers` is provided)
- `layers` — optional list of `{name, thickness}` dicts (exterior → interior);
  e.g. `[{name:"brick", thickness:110}, {name:"insulation", thickness:75},
  {name:"plaster", thickness:15}]`; total thickness = sum of layers
- `id` — optional wall identifier for referencing by doors/windows

**Output:**
```json
{
  "op": "arch_wall", "id": "...",
  "start": [x, y], "end": [x, y],
  "height_mm": 3000, "thickness_mm": 200,
  "layers": [...],
  "length_mm": 5000,
  "gross_area_mm2": 15000000,
  "gross_volume_mm3": 3000000000
}
```

---

### `arch_door`

Create a parametric door hosted in a wall.

**Input:**
- `width` (required) — clear opening width mm (> 0)
- `height` (required) — clear opening height mm (> 0)
- `wall_ref` (required) — host wall id
- `position_along_wall` (required) — distance from wall start to near door edge mm (>= 0)
- `wall_length` (required) — host wall length mm
- `wall_height` (required) — host wall height mm
- `wall_thickness` (required) — host wall thickness mm
- `swing` — `hinged_left` | `hinged_right` | `double` | `sliding` | `folding` | `pivot`  
  Default: `hinged_left`
- `id` — optional door identifier

**Output:**
```json
{
  "op": "arch_door", "id": "...", "wall_ref": "...",
  "width_mm": 900, "height_mm": 2100, "swing": "hinged_left",
  "cut_box": {"width_mm": 900, "height_mm": 2100, "depth_mm": 200},
  "opening_volume_mm3": 37800000,
  "panel_params": {"panel_width_mm": 900, "panel_height_mm": 2100, "swing": "hinged_left"}
}
```

---

### `arch_window`

Create a parametric window hosted in a wall.

**Input:**
- `width` (required) — clear opening width mm (> 0)
- `height` (required) — clear opening height mm (> 0)
- `sill_height` (required) — sill above floor mm (>= 0); typical 900 mm
- `wall_ref` (required) — host wall id
- `position_along_wall` (required) — distance from wall start to near edge mm
- `wall_length`, `wall_height`, `wall_thickness` (required) — host wall dims
- `operation` — `fixed` | `casement` | `sliding` | `awning` | `hopper` | `tilt_turn` | `louvre`  
  Default: `casement`
- `id` — optional identifier

**Output:** includes `head_height_mm = sill_height + height`, `opening_volume_mm3`,
`cut_box` (with `sill_height_mm`), and `panel_params`.

---

### `arch_slab`

Create a parametric horizontal slab (floor plate, roof deck, etc.).

**Input:**
- `outline` (required) — polygon vertices `[[x1,y1],[x2,y2],...]` mm (>= 3 points)
- `thickness` (required) — slab thickness mm (> 0)
- `level` — Z-elevation of slab top surface mm (default 0)
- `id` — optional identifier

**Output:**
```json
{
  "op": "arch_slab", "id": "...",
  "outline": [[...], ...],
  "thickness_mm": 200, "level_mm": 3000,
  "area_mm2": 24000000,
  "volume_mm3": 4800000000
}
```

Area is computed by the shoelace formula; CW and CCW orderings both work.

---

### `arch_opening`

Create a generic void (rectangular or arched) cut into a wall.

**Input:**
- `width` (required) — opening width mm (> 0)
- `height` (required) — rectangular portion height mm (> 0)
- `wall_ref` (required) — host wall id
- `position_along_wall` (required) — distance from wall start mm
- `wall_length`, `wall_height`, `wall_thickness` (required)
- `sill_height` — bottom of opening above floor mm (default 0)
- `arch_type` — `rectangular` (default) | `arched`  
  For `arched`: a semicircular head of radius `width/2` is added above `height`;
  total opening area = `width × height + π × (width/2)² / 2`
- `id` — optional identifier

**Output:** includes `arch_rise_mm`, `cut_params`, `opening_volume_mm3`.

---

### `arch_wall_with_openings`

Compose a wall with hosted doors/windows/openings and compute net volume.

**Input:**
- `wall` (required) — output dict from `arch_wall` (must have `ok: true`)
- `openings` (required) — list of dicts from `arch_door`, `arch_window`, or
  `arch_opening` (each must have `ok: true`); pass `[]` for no openings

**Output:**
```json
{
  "ok": true,
  "wall": {...},
  "openings": [...],
  "gross_volume_mm3": 3000000000,
  "total_opening_volume_mm3": 75600000,
  "net_volume_mm3": 2924400000
}
```

Returns `{ok: false, errors: [...]}` if any opening is invalid.

---

## Typical workflow

```
1. arch_wall  start:[0,0]  end:[5000,0]  height:3000  thickness:200  id:"w-01"
   → wall_recipe

2. arch_door  width:900  height:2100  wall_ref:"w-01"
              position_along_wall:500
              wall_length:5000  wall_height:3000  wall_thickness:200
   → door_recipe

3. arch_window  width:1200  height:1500  sill_height:900  wall_ref:"w-01"
                position_along_wall:2500
                wall_length:5000  wall_height:3000  wall_thickness:200
   → window_recipe

4. arch_wall_with_openings  wall:wall_recipe  openings:[door_recipe, window_recipe]
   → {ok:true, net_volume_mm3: ..., gross_volume_mm3: ...}
```

---

## Notes

- All tools are **pure-Python**; no OCC dependency, no DB write.
- All dimensions are **millimetres** — inputs and outputs.
- Fit validation is done before any volumes are computed; if a door/window
  overflows the wall extents the individual tool returns `{ok: false}` so
  `arch_wall_with_openings` will also fail cleanly with the reason.
- Layer order is **exterior → interior**; total thickness = sum of layers.
- `arch_opening` arched volumes include the semicircular head area.
