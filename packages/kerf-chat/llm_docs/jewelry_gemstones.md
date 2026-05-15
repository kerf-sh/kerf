# Jewelry: Gemstone Generator + Gem-Seat Boolean

## Overview

Two LLM tools handle the jewelry gemstone workflow:

| Tool | Write | Purpose |
|------|-------|---------|
| `jewelry_create_gemstone` | yes | Append a `gemstone` parametric solid node to a `.feature` file |
| `jewelry_cut_gem_seat`    | yes | Append a `gem_seat` cutter node; optionally chain a `boolean` cut |

---

## Supported cuts

### Classic cuts

| Key | Description | Industry name |
|-----|-------------|---------------|
| `round_brilliant` | 57/58 facets — the GIA standard | RBC |
| `princess` | Square modified brilliant | — |
| `oval` | Elliptical modified brilliant | — |
| `emerald` | Rectangular step cut | — |
| `marquise` | Boat-shaped modified brilliant | — |
| `pear` | Teardrop modified brilliant | — |
| `cushion` | Soft-square modified brilliant | — |

### Fancy cuts

| Key | Description | Notes |
|-----|-------------|-------|
| `radiant` | Cropped-corner rectangular modified brilliant | 70 facets, L:W ≈ 1.33:1 |
| `asscher` | Square step cut with heavy corner crops | High crown, step_rows=3 |
| `trillion` | Equilateral triangular modified brilliant | 43 facets, equilateral |
| `heart` | Heart-shaped modified brilliant | 59 facets, V-cleft |
| `baguette` | Narrow rectangular step cut | 3:1 L:W, step_rows=2 |
| `briolette` | All-facet elongated teardrop, no table | 8 facet rows, no table |

---

## Carat ↔ mm formula

All cuts use a cubic approximation calibrated to the stone's material density:

```
ref_mm_material = ref_mm_diamond × (rho_diamond / rho_material) ^ (1/3)
carat = (dim_mm / ref_mm_material) ^ 3
dim_mm = ref_mm_material × carat ^ (1/3)
```

`dim_mm` is the **girdle diameter** for `round_brilliant`, the **long axis**
for all other cuts.

Default material is `diamond` for backward compatibility.

### Reference dimensions at 1 ct (diamond, 3.51 g/cm³)

| Cut | `ref_mm` at 1 ct | Notes |
|-----|-----------------|-------|
| round_brilliant | 6.5 | GIA table |
| princess | 5.5 | square face; depth ~68% |
| oval | 7.7 | 1.35:1 L:W ratio |
| emerald | 7.0 | 1.4:1, step cut shallower |
| marquise | 10.0 | 2:1 L:W |
| pear | 8.0 | 1.6:1 |
| cushion | 5.5 | similar to princess |
| radiant | 6.0 | cropped rectangular brilliant |
| asscher | 5.5 | square step, deep crown |
| trillion | 7.0 | equilateral triangle, wide face |
| heart | 6.5 | same volume class as round brilliant |
| baguette | 5.0 | narrow bar, shallow |
| briolette | 5.5 | elongated teardrop |

---

## Default proportions (industry standard)

### Round brilliant (GIA ideal / Tolkowsky)

| Parameter | Value |
|-----------|-------|
| Table % | 57 % |
| Crown angle | 34.5° |
| Crown height | 16.2 % |
| Pavilion angle | 40.75° |
| Pavilion depth | 43.1 % |
| Girdle | 2.5 % |
| Total depth | ~62 % |
| Facets | 57 |

### Fancy cut highlights

| Cut | Table % | Crown° | Pav° | Depth % | Aspect | Extras |
|-----|---------|--------|------|---------|--------|--------|
| radiant | 62 | 32 | 41 | ~58 | 0.75 | corner_cut_ratio=0.10 |
| asscher | 60 | 25 | 43 | ~60 | 1.0 | step_rows=3, corner_cut_ratio=0.20 |
| trillion | 55 | 34 | 41 | ~51 | 1.0 | sides=3 |
| heart | 56 | 34.5 | 40.75 | ~60 | 0.98 | cleft_depth_pct=10 |
| baguette | 70 | 8 | 43 | ~46 | 0.33 | step_rows=2 |
| briolette | 0 | 30 | 45 | ~102 | 0.50 | facet_rows=8 (no table) |

All other cuts follow GIA/AGS published ranges. Override any parameter via
the tool's optional kwargs (`table_pct`, `crown_angle_deg`, `pavilion_angle_deg`,
`girdle_pct`, `aspect_ratio`).

---

## Schema: `gemstone` feature node

```json
{
  "id": "gemstone-1",
  "op": "gemstone",
  "cut": "round_brilliant",
  "diameter_mm": 6.5,
  "aspect_ratio": 1.0,
  "table_pct": 57.0,
  "crown_angle_deg": 34.5,
  "crown_height_pct": 16.2,
  "pavilion_angle_deg": 40.75,
  "pavilion_depth_pct": 43.1,
  "girdle_pct": 2.5,
  "total_depth_pct": 61.8,
  "material": "diamond",
  "extras": { "facet_count": 57, "culet": "none" },
  "position": [0, 0, 0],
  "orientation_deg": [0, 0, 0]
}
```

The OCCT worker's `opGemstone` builds a closed `TopoDS_Solid` from this node:
pavilion cone (apex down) + girdle cylinder + crown truncated cone.

---

## Schema: `gem_seat` feature node

```json
{
  "id": "gem_seat-1",
  "op": "gem_seat",
  "cut": "round_brilliant",
  "diameter_mm": 6.5,
  "girdle_radius_mm": 3.3,
  "pavilion_depth_mm": 2.8,
  "pavilion_angle_deg": 40.75,
  "girdle_height_mm": 0.18,
  "bearing_cone_half_angle": 40.75,
  "bearing_cone_top_radius": 3.3,
  "bearing_cone_bottom_radius": 0.033,
  "culet_depth_mm": 0.1,
  "crown_relief_depth_mm": 0.3,
  "crown_relief_half_angle": 17.25,
  "through_hole": false,
  "through_hole_radius_mm": 0.0,
  "total_cutter_depth_mm": 3.38,
  "position": [0, 0, 0],
  "orientation_deg": [0, 0, 0]
}
```

---

## Seat-boolean algorithm

```
seat cutter = bearing_cone ∪ girdle_ledge_cylinder ∪ crown_relief_cone
             [ ∪ through_hole_cylinder  if through_hole=true ]

host_with_seat = feature_boolean(
    file_id, target_a_id=<ring_shank>, target_b_id=<seat_id>, kind="cut"
)
```

### Step-by-step

1. Call `jewelry_create_gemstone` to place the gemstone solid.
2. Call `jewelry_cut_gem_seat` with the same cut/size, matching `position`
   and `orientation_deg`.  Pass `auto_cut_host_id=<ring_shank_node_id>` to
   skip step 3.
3. (Without `auto_cut_host_id`) call `feature_boolean`:
   - `target_a_id` = ring shank / bezel node id
   - `target_b_id` = seat node id returned by step 2
   - `kind` = `"cut"`

The gemstone solid (step 1) and the seat cutter (step 2) are independent
feature nodes.  The seat cutter is NOT automatically subtracted — always do
the boolean cut explicitly or via `auto_cut_host_id`.

---

## Clearance defaults

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `girdle_clearance_mm` | 0.05 | Radial play so stone drops in |
| `culet_clearance_mm` | 0.10 | Tool room / light below pavilion |
| `seat_allowance_mm` | 0.02 | Axial bearing-ledge tolerance |
| `crown_relief_mm` | 0.30 | Countersink depth above girdle |

Tighten `girdle_clearance_mm` to 0.02 for a press-fit (gypsy/flush set).
Increase to 0.10 for a bezel set where the metal will be pushed over.

---

## Worked example: 1 ct round brilliant solitaire

```
# 1. Create gemstone (1 ct round brilliant, table facing +Z)
jewelry_create_gemstone(
    file_id="<feature_file_uuid>",
    cut="round_brilliant",
    carat=1.0,
    position=[0, 0, 5],   # centre of girdle at z=5
    material="diamond"
)
# → gemstone-1, diameter_mm=6.5, total_depth_mm=4.02

# 2. Cut seat in ring shank (ring shank is feature node "sweep1-1")
jewelry_cut_gem_seat(
    file_id="<feature_file_uuid>",
    cut="round_brilliant",
    carat=1.0,
    position=[0, 0, 5],
    auto_cut_host_id="sweep1-1"
)
# → seat_id=gem_seat-1, boolean_id=boolean-1

# The feature tree now contains:
#   sweep1-1     — ring shank solid
#   gemstone-1   — diamond solid (visual only; not subtracted from shank)
#   gem_seat-1   — seat cutter solid
#   boolean-1    — sweep1-1 CUT gem_seat-1  (the final ring + seat)
```

---

## .gem library file kind

`.gem` files (kind `"gem"`) store reusable gemstone specs in JSON.  Use the
`files` API to create, read, and version them like any other project file.
Migration `060_kind_gem.sql` adds `'gem'` to the `files_kind_check`
constraint.

---

## Known limitations / deferred

- The OCCT worker (`opGemstone`, `opGemSeat`) is not yet implemented; nodes
  are stored in the feature tree but will show a "worker op not implemented"
  error in the evaluator.  Pure-Python geometry math (proportions, seat
  clearances) is fully functional.
- FeatureView dropdown does not yet list the 6 new fancy cuts (radiant, asscher,
  trillion, heart, baguette, briolette).  The Python spec + generic worker op
  are complete; a consolidated frontend pass will add them to the UI enum.
- Setting styles (prong, bezel, channel, pavé) are not yet modelled — only
  the seat void is generated.
