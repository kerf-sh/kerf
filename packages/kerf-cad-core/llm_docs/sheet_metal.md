# Sheet Metal Tools (`sheet_metal.py`, `sheet_metal_bend_table.py`)

Sheet-metal feature tools: flanged B-rep creation (T-1), neutral-axis
unfold calculation (T-2), flat-pattern DXF export (T-3), and per-material
bend-table / K-factor lookup (T-4).

---

## When to use

Reach for these tools when the user asks about:

- creating a sheet-metal part with a folded flange at a given bend angle and radius
- computing the developed (flat) length of a bent part before cutting
- exporting a flat-pattern outline and bend lines as DXF
- looking up the correct K-factor or bend allowance for a material / process combination
- spring-back estimate for air-bend / bottoming / coining

---

## Tools

### `sheet_metal_flange` (T-1)

Append a `sheet_metal_flange` node to a `.feature` file.  The OCCT worker
produces a single folded solid: base plate → bend arc → flange wall.

**Required:** `file_id`, `edge_ref`, `flange_length`, `bend_angle_deg`,
`bend_radius`, `thickness`, `base_width`, `base_depth`

**Optional:** `k_factor` (default 0.44), `id`

| Param | Constraint | Notes |
|-------|-----------|-------|
| `edge_ref` | non-empty str | e.g. `"top-front"`, `"top-left"`, `"edge-0"` |
| `flange_length` | > 0 mm | straight wall after bend arc |
| `bend_angle_deg` | (0, 180] | 90° = right angle |
| `bend_radius` | > 0 mm | inside radius |
| `thickness` | > 0 mm | sheet wall thickness |
| `k_factor` | (0, 1) | 0.33 hard/tool steel · 0.44 mild steel · 0.50 aluminium |
| `base_width`, `base_depth` | > 0 mm | blank plate dimensions |

**Returns:** `{file_id, id, op:"sheet_metal_flange", edge_ref, flange_length, bend_angle_deg, ...}`

---

### `sheet_metal_unfold` (T-2)

Compute the developed length using the neutral-axis bend-allowance formula:

```
BA = angle_rad × (bend_radius + k_factor × thickness)
developed_length = base_length + BA + flange_length
```

Pure Python; no file writes.

**Required:** `base_length` (mm), `flange_length`, `bend_angle_deg`, `bend_radius`, `thickness`
**Optional:** `k_factor` (default 0.44)

**Note:** `base_length` = `base_depth` for front/back bends; `base_width` for left/right bends.

**Returns:**
```json
{
  "bend_allowance": 1.508,
  "developed_length": 71.508,
  "bend_lines": [
    {"position": 50.0, "label": "bend-start"},
    {"position": 51.508, "label": "bend-end"}
  ]
}
```

---

### `sheet_metal_flat_pattern` (T-3)

Emit a minimal DXF R12 string for the flat-pattern.  Outline is a closed
POLYLINE on layer `"0"`; bend lines are `LINE` entities on layer `"BEND"`.
No external DXF library required.

**Required:** `base_length`, `width`, `flange_length`, `bend_angle_deg`, `bend_radius`, `thickness`
**Optional:** `k_factor`

**Returns:** `{dxf: "...DXF R12 string..."}`

---

### `sheet_metal_bend_table` (T-4, `sheet_metal_bend_table.py`)

Per-material K-factor / bend-allowance / bend-deduction lookup by
material × thickness × inner radius × bend angle × process.

**Required:** `material`, `thickness` (mm), `inner_radius` (mm), `angle_deg`
**Optional:** `process` (`"air"` / `"bottoming"` / `"coining"`, default `"air"`)

**Returns:**
```json
{
  "ok": true,
  "k_factor": 0.44,
  "bend_allowance": ...,
  "bend_deduction": ...,
  "setback": ...,
  "neutral_axis_offset": ...,
  "spring_back_angle_deg": ...
}
```

K-factor formula (DIN 6935):
- r/t < 1 → K ≈ 0.33
- r/t 1–3 → linear interpolation to K_max
- r/t ≥ 3 → K_max (material ceiling)

Process modifiers: bottoming ×0.90, coining ×1.10.

---

## Supported input contract

- Sheet metal tools operate on `.feature` files via the OCCT worker (T-1).
- T-2 / T-3 are pure-Python computation; they do not read or write files.
- T-4 uses built-in material tables (mild steel, stainless, aluminium,
  copper, tool steel) plus custom tables loaded via `custom_table_load`.
- Multi-flange (successive bend ops) is deferred to T-4+.

---

## Usage examples

**Create a 90° flanged part (50×50 mm base, 20 mm flange):**

```
sheet_metal_flange
  file_id: "<uuid>"  edge_ref: "top-front"
  base_width: 50  base_depth: 50  thickness: 2.0
  flange_length: 20  bend_angle_deg: 90  bend_radius: 3.0  k_factor: 0.44
→ {id:"sheet_metal_flange-1", op:"sheet_metal_flange"}
```

**Compute developed length:**

```
sheet_metal_unfold
  base_length: 50  flange_length: 20  bend_angle_deg: 90
  bend_radius: 3.0  thickness: 2.0  k_factor: 0.44
→ {bend_allowance:4.398, developed_length:74.398, bend_lines:[{position:50},{position:54.398}]}
```

**K-factor lookup for 2 mm mild steel, 3 mm inside radius, air-bend:**

```
sheet_metal_bend_table
  material: "mild_steel"  thickness: 2.0  inner_radius: 3.0  angle_deg: 90
→ {k_factor:0.44, bend_allowance:4.398, spring_back_angle_deg:0.9}
```

---

## References

DIN 6935 — *Cold bending of flat products*, neutral-axis position and bend-allowance formula.
*Machinery's Handbook*, 29th ed., industrial press — K-factor tables and spring-back coefficients.
Hosford, W.F., Caddell, R.M. — *Metal Forming: Mechanics and Metallurgy*, 4th ed. — spring-back formula §7.
