# kerf-landscape

Landscape and site-design tools for Kerf. Covers terrain grading, surface drainage, planting design, and hardscape layout. All functions are pure Python — no numpy/scipy required for the base install.

---

## Modules

### `grading.py` — DEM contours and cut/fill volumes

#### `contours_from_dem(dem, x_coords, y_coords, levels) → dict`

Extract iso-contour line segments from a 2-D DEM grid using marching squares.

- **dem**: 2-D list of floats `[ny][nx]` — elevation in metres.
- **x_coords**: monotonically increasing x positions [m].
- **y_coords**: monotonically increasing y positions [m].
- **levels**: list of contour elevations to extract [m].

Returns `{"ok", "contours": [{"level", "segments": [(x0,y0,x1,y1),...]}]}`.

A flat surface at the contour level returns zero segments (marching-squares cases 0 and 15 produce no output).

```python
from kerf_landscape.grading import contours_from_dem

dem = [[0.0, 0.0, 2.0, 2.0],
       [0.0, 0.0, 2.0, 2.0]]
x = [0.0, 1.0, 2.0, 3.0]
y = [0.0, 1.0]
result = contours_from_dem(dem, x, y, levels=[1.0])
# result["contours"][0]["segments"] → list of (x0,y0,x1,y1) line segments
```

#### `cut_fill_volumes(dem_existing, dem_design, cell_width, cell_height) → dict`

Prismatoid estimate of earthwork volumes.

```
cut_m3  = Σ max(0,  z_existing − z_design) · cell_area
fill_m3 = Σ max(0,  z_design − z_existing) · cell_area
net_m3  = fill_m3 − cut_m3
```

Returns `{"ok", "cut_m3", "fill_m3", "net_m3"}`.

#### `grade_surface(dem, x_coords, y_coords, target_grade, origin_xy, direction) → dict`

Apply a uniform planar grade to a DEM patch.  The design surface passes through `origin_xy` at the existing elevation and falls at `target_grade` (rise/run) in the given direction vector.

Returns `{"ok", "dem_design", "origin_elev"}`.

---

### `drainage.py` — Surface runoff and flow accumulation

#### `rational_method(C, i_in_per_hr, A_acres) → dict`

Peak surface runoff via the Rational Method.

```
Q = C · i · A    [cfs]   (ASCE/WEF MoEP 92, §3.2)
```

| Parameter | Description |
|---|---|
| C | Runoff coefficient (0–1) |
| i_in_per_hr | Rainfall intensity [in/hr] |
| A_acres | Drainage area [acres] |

Returns `{"ok", "Q_cfs", "Q_m3s", "C", "i_in_per_hr", "A_acres"}`.

**Analytic oracle**: C=0.6, i=2 in/hr, A=1 acre → Q = 1.2 cfs exactly.

```python
from kerf_landscape.drainage import rational_method

r = rational_method(C=0.6, i_in_per_hr=2.0, A_acres=1.0)
print(r["Q_cfs"])   # 1.2
print(r["Q_m3s"])   # ≈ 0.03398
```

#### `flow_accumulation_d8(dem, cell_size) → dict`

D8 single-direction flow routing (O'Callaghan & Mark, 1984).  Each cell drains to its steepest descent neighbour.  The accumulation at each cell is the count of upstream cells (including itself).

Returns `{"ok", "accumulation": [[int]], "outlets": [(row, col)]}`.

On a constant slope, all cells route to the low edge; the low-row accumulations equal the number of rows in each column.

#### `catchment_runoff(dem, x_coords, y_coords, C_grid, design_storm_in_per_hr) → dict`

Full-catchment peak runoff: combines D8 flow accumulation with the Rational Method per outlet cell.

Returns `{"ok", "total_Q_cfs", "total_Q_m3s", "accumulation", "C_weighted"}`.

---

### `planting.py` — Xeriscape plant catalogue

A curated catalogue of 20 drought-tolerant species with USDA hardiness zones, WUCOLS water-use ratings, and mature dimensions.

#### `get_plant_catalogue() → list[dict]`

Return all plants.  Each entry has:

| Key | Type | Description |
|---|---|---|
| name | str | Common name |
| scientific_name | str | Binomial |
| type | str | tree / shrub / perennial / grass / groundcover / succulent |
| zone_min / zone_max | int | USDA hardiness zone range |
| water_use | str | very-low / low / moderate / high (WUCOLS) |
| mature_height_m | float | metres |
| spread_m | float | canopy spread [m] |
| spacing_m | float | recommended on-centre spacing [m] |
| sun | str | full-sun / part-shade / full-shade |

#### `filter_by_zone(catalogue, zone) → list[dict]`

Return only plants hardy to USDA zone `zone` (integer).

#### `filter_by_water_use(catalogue, max_water_use) → list[dict]`

Return plants with water use ≤ `max_water_use`.  Level order: very-low < low < moderate < high.

#### `plant_spacing_grid(plant, area_width, area_depth, offset_rows=True) → dict`

Generate a planting grid for a rectangular bed.  With `offset_rows=True` (default) uses a triangular grid (row spacing = `spacing × √3/2`) for higher coverage efficiency.

Returns `{"ok", "positions": [(x, y),...], "count", "spacing_m", "row_spacing_m"}`.

#### `plant_water_budget(plants, area_m2, eto_mm_per_year) → dict`

Annual irrigation estimate using WUCOLS landscape coefficient (kl):
```
very-low → kl = 0.1
low      → kl = 0.3
moderate → kl = 0.6
high     → kl = 1.0

Volume [L] = kl × ETo [mm] × Area [m²]
```

Returns `{"ok", "water_L_per_year", "water_m3_per_year", "breakdown"}`.

---

### `hardscape.py` — Paver patterns and retaining walls

#### `paver_pattern(pattern, area_width, area_depth, unit_w, unit_h, joint) → dict`

Generate paver positions for a rectangular area.

Supported patterns:
- `"running-bond"` — alternating row offset of half a unit width
- `"stack-bond"` — aligned grid
- `"herringbone-45"` — 45-degree herringbone
- `"basketweave"` — alternating horizontal/vertical pairs

Returns `{"ok", "pattern", "positions": [{"x","y","angle_deg","w","h"}], "count", "coverage_pct", "area_m2"}`.

#### `paver_material_estimate(pattern_result, paver_thickness_m, waste_pct) → dict`

Material takeoff from a paver pattern result.  Applies a percentage waste allowance (default 5 %).

Returns `{"ok", "paver_count", "paver_count_with_waste", "paver_volume_m3", "base_area_m2", "coverage_pct"}`.

#### `retaining_wall_layout(height, length, wall_type, soil_phi_deg, soil_gamma, surcharge) → dict`

Preliminary retaining wall sizing using Rankine active earth pressure theory (Rankine, 1857):

```
Ka = tan²(45° − φ/2)
P_active = ½ Ka γ H² + Ka q H      [N/m]
```

Wall types: `"gravity"` | `"cantilevered"` | `"segmental"`.

Returns `{"ok", "Ka", "P_active_N_per_m", "P_total_kN", "resultant_height_m", "min_base_width_m", "moments_about_toe", "wall_type"}`.

**Analytic oracle**: for φ = 30°, Ka = tan²(30°) = 1/3.

---

## LLM Tools

Registered at startup by `kerf_landscape.plugin:register`:

| Tool | Description |
|---|---|
| `landscape_contours` | Extract contour segments from a DEM |
| `landscape_cut_fill` | Cut/fill earthwork volume |
| `landscape_runoff` | Rational-method peak runoff (Q = CiA) |
| `landscape_plants` | Query plant catalogue by zone / water use |
| `landscape_paver_pattern` | Paver layout positions |
| `landscape_retaining_wall` | Rankine earth pressure + wall sizing |

---

## Analytic oracle citations

| Formula | Reference | Oracle |
|---|---|---|
| Q = C·i·A | ASCE/WEF MoEP 92, §3.2 (1992) | C=0.6, i=2 in/hr, A=1 ac → Q=1.2 cfs |
| Ka = tan²(45−φ/2) | Rankine (1857), Phil. Trans. R. Soc. | φ=30° → Ka=1/3 |
| P = ½KaγH² | Das & Sivakugan, *Principles of Foundation Engineering*, 9th ed. | — |
| kl landscape coefficients | WUCOLS IV (UC Cooperative Extension, 2014) | — |
| D8 routing | O'Callaghan & Mark (1984), CVGIP 28:323–344 | — |

---

## Limitations

- Contour extraction uses marching squares on the raw grid; no smoothing or polyline chaining is applied.
- Cut/fill uses a per-cell prismatoid approximation (not a full triangulated surface mesh).
- Retaining wall sizing is preliminary only; a licensed structural engineer must review any built wall.
- Plant catalogue is a curated seed list; add species via `_CATALOGUE` in `planting.py`.
- D8 flow routing does not resolve flat areas or pits (no pit-filling step).
