# Jewelry: Gemstone Generator + Gem-Seat Boolean

## Overview

Four LLM tools handle the jewelry gemstone workflow:

| Tool | Write | Purpose |
|------|-------|---------|
| `jewelry_create_gemstone` | yes | Append a `gemstone` parametric solid node to a `.feature` file |
| `jewelry_cut_gem_seat`    | yes | Append a `gem_seat` cutter node; optionally chain a `boolean` cut |
| `jewelry_gem_report`      | no  | Read-only gemologist-style proportion report + 4Cs estimates |
| `jewelry_gem_catalog`     | no  | Read-only birthstone / gem property catalog (by name or month) |

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

### Historical / specialty cuts

These map to existing facet families — no OCCT worker change needed.

| Key | Description | Facet family | Notes |
|-----|-------------|--------------|-------|
| `old_european` | Pre-1930s round brilliant precursor | round_brilliant | High crown ~40°, small table ~40%, large culet |
| `old_mine` | Victorian cushion brilliant | cushion | High crown ~38°, large culet, square outline |
| `rose_cut` | Flat-base dome top, triangular facets | round_brilliant | No table, no pavilion; 24 facets |
| `single_cut` | Simplified 17-facet brilliant | round_brilliant | Melee side stones |
| `french_cut` | Square step with X-pattern table | princess | Art-deco; 1 step row, sharp corners |
| `half_moon` | D-shaped semi-circular fancy | oval | Straight chord edge, curved girdle |
| `trapezoid` | Tapered step-cut side stone | baguette | step_rows=2, taper_ratio=0.80 |
| `kite` | Arrowhead four-sided angular fancy | trillion | 4 sides, acute point |
| `bullet` | Tapered fancy with pointed base | pear | Flat/rounded top, pointed bottom |
| `tapered_baguette` | Baguette with angled short ends | baguette | step_rows=2, taper_ratio=0.70 |
| `lozenge` | Rhombus four-point step cut | marquise | step_rows=2, 1.5:1 L:W |
| `shield` | Five-sided shield-shaped brilliant | trillion | 5 sides, wide top tapering to point |
| `calf_head` | Wide pear variant (bouche) | pear | Broader than standard pear; aspect ≈ 0.78 |

### Step / mixed cuts

These also map to existing facet families — no OCCT worker change needed.

| Key | Description | Facet family | Notes |
|-----|-------------|--------------|-------|
| `portuguese` | Round step + brilliant hybrid; many concentric step rows; high fire | round_brilliant | step_rows_crown=4, 73 facets typical |
| `ceylon` | Barion hybrid: brilliant crown + step pavilion | emerald | Rectangular aspect ~0.75, step_rows=3, corner_cut=0.12 |
| `flanders` | Square brilliant with softly cropped corners | princess | aspect=1.0, corner_cut_ratio=0.05 (lighter than princess), 65 facets |
| `square_emerald` | Square step cut (equal L:W emerald; "Quadrillion") | emerald | aspect=1.0, step_rows=3, corner_cut=0.12 |

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
| old_european | 6.5 | same footprint as round brilliant |
| old_mine | 5.5 | cushion outline; ~same depth as princess |
| rose_cut | 7.8 | flat base = more spread per carat |
| single_cut | 4.1 | tiny melee; shallow 17-facet |
| french_cut | 5.0 | small square step |
| half_moon | 8.5 | half-oval; wide face, shallow |
| trapezoid | 6.5 | trapezoidal step |
| kite | 6.0 | kite/arrowhead; triangular derivative |
| bullet | 5.5 | tapered pear; similar to small pear |
| tapered_baguette | 5.2 | baguette with angled ends |
| lozenge | 6.5 | rhombus step cut |
| shield | 6.8 | irregular pentagon; large face |
| calf_head | 8.5 | wide low-set pear variant |
| portuguese | 6.5 | round step+brilliant; same spread as round brilliant |
| ceylon | 6.5 | barion hybrid; similar to radiant |
| flanders | 5.5 | square brilliant; similar to princess |
| square_emerald | 5.5 | square step cut; same footprint as asscher |

---

## Coloured-stone density correction

Pass `material` or `density_g_cm3` to get accurate carat weights for coloured
stones.  The formula scales the reference dimension as:

```
ref_mm_material = ref_mm_diamond × (3.51 / rho) ^ (1/3)
```

so that volume × density = 0.2 g (1 carat) for any cut shape.

### Built-in density table (g/cm³, GIA Gem Reference Guide)

| Material | Density | Notes |
|----------|---------|-------|
| diamond | 3.51 | calibration baseline |
| ruby | 3.99 | corundum |
| sapphire | 4.00 | corundum |
| emerald | 2.72 | beryl |
| amethyst | 2.65 | quartz |
| citrine | 2.65 | quartz |
| aquamarine | 2.72 | beryl |
| morganite | 2.71 | beryl |
| topaz | 3.53 | — |
| garnet | 3.78 | pyrope–almandine |
| spinel | 3.60 | — |
| tanzanite | 3.35 | zoisite |
| peridot | 3.32 | — |
| tourmaline | 3.10 | — |
| opal | 2.08 | — |
| moonstone | 2.56 | orthoclase feldspar |
| alexandrite | 3.73 | chrysoberyl |
| zircon | 4.67 | high type |
| pearl | 2.71 | nacre |

For a stone not in this list, pass `density_g_cm3=<value>` explicitly.
Unknown material names fall back to diamond silently (backward-compatible).

**Sources:** GIA Gem Reference Guide (Liddicoat, 1995), GIA Gemology Reference
(gia.edu/gems-gemology), GIA Gem Encyclopedia (2014 ed.), International Gem
Society gem property tables.

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

### Historical / specialty cut proportions

| Cut | Table % | Crown° | Pav° | Depth % | Aspect | Family |
|-----|---------|--------|------|---------|--------|--------|
| old_european | 40 | 40 | 40 | ~68 | 1.0 | round_brilliant |
| old_mine | 40 | 38 | 41 | ~66 | 1.0 | cushion |
| rose_cut | 0 | 20 | 1 | ~27 | 1.0 | round_brilliant |
| single_cut | 65 | 30 | 40 | ~54 | 1.0 | round_brilliant |
| french_cut | 68 | 28 | 43 | ~57 | 1.0 | princess |
| half_moon | 56 | 34.5 | 40.75 | ~59 | 0.56 | oval |
| trapezoid | 65 | 10 | 43 | ~47 | 0.55 | baguette |
| kite | 55 | 34 | 41 | ~54 | 0.65 | trillion |
| bullet | 55 | 33 | 41 | ~58 | 0.60 | pear |
| tapered_baguette | 70 | 8 | 43 | ~46 | 0.30 | baguette |
| lozenge | 58 | 18 | 42 | ~53 | 0.65 | marquise |
| shield | 55 | 35 | 41 | ~57 | 0.85 | trillion |
| calf_head | 55 | 32 | 40 | ~57 | 0.78 | pear |

### Step / mixed cut proportions

| Cut | Table % | Crown° | Pav° | Depth % | Aspect | Family |
|-----|---------|--------|------|---------|--------|--------|
| portuguese | 55 | 35 | 40.75 | ~63 | 1.0 | round_brilliant |
| ceylon | 58 | 33 | 41 | ~59 | 0.75 | emerald |
| flanders | 67 | 30 | 42 | ~56 | 1.0 | princess |
| square_emerald | 62 | 14 | 44 | ~54 | 1.0 | emerald |

All cuts follow GIA/AGS published ranges. Override any parameter via
the tool's optional kwargs (`table_pct`, `crown_angle_deg`, `pavilion_angle_deg`,
`girdle_pct`, `aspect_ratio`).

---

## Tool: `jewelry_gem_report` (read-only)

Returns a gemologist-style proportion report for any cut + size without
writing anything.  Use this before `jewelry_create_gemstone` to inspect
proportions or verify carat estimates.

### Input

```
cut          : string  (required) — any GEMSTONE_CUTS key
carat        : number  (one of)   — stone weight in carats
diameter_mm  : number  (one of)   — primary dimension in mm
material     : string  (optional) — density lookup (default: 'diamond')
density_g_cm3: number  (optional) — explicit density override
```

### Output schema

```json
{
  "cut": "round_brilliant",
  "facet_family": "round_brilliant",
  "material": "diamond",
  "spread_mm": 6.5,
  "width_mm": 6.5,
  "depth_mm": 4.02,
  "carat_est": 1.0,
  "table_pct": 57.0,
  "total_depth_pct": 61.8,
  "crown_height_pct": 16.2,
  "pavilion_depth_pct": 43.1,
  "girdle_pct": 2.5,
  "crown_angle_deg": 34.5,
  "pavilion_angle_deg": 40.75,
  "aspect_ratio": 1.0,
  "lw_ratio": 1.0,
  "proportion_grade": "Excellent",
  "colour_scale_hint": "estimate — not a lab grade: GIA D–Z scale ...",
  "clarity_hint": "estimate — not a lab grade: GIA FL / IF / VVS1-2 ...",
  "recommended_setting": "prong (4 or 6 claw) solitaire"
}
```

### Proportion grade heuristic

The `proportion_grade` field applies GIA/AGS ideal-window ranges
per cut family across four indicators (table %, depth %, crown angle,
pavilion angle):

| Misses | Grade |
|--------|-------|
| 0 | Excellent |
| 1 | Very Good |
| 2 | Good |
| 3+ | Fair |

Default proportions for round brilliant (`Tolkowsky ideal`) grade
**Excellent**.  Historical cuts (old_european, rose_cut, etc.) use
their own appropriate windows.

### 4Cs estimate fields (new — additive, back-compat)

These three fields are **clearly labelled as estimates — NOT lab grades**.
They are heuristic placeholders derived from the material type and cut only.

| Field | Description |
|-------|-------------|
| `colour_scale_hint` | Diamond: GIA D–Z scale explanation. Coloured stone: GIA hue/saturation/tone dimensions. Always includes "estimate — not a lab grade" label. |
| `clarity_hint` | Diamond: GIA FL–I3 scale; eye-clean threshold per cut. Coloured stone: GIA clarity type (I/II/III). Step cuts include a note that inclusions are more visible. Always includes "estimate — not a lab grade" label. |
| `recommended_setting` | Trade-standard setting suggestion for the cut and size bracket (melee < 3.5 mm, small 3.5–5 mm, medium 5–8 mm, large ≥ 8 mm). Source: RhinoGold / GIA setting design guidelines. |

### Example

```
# Inspect a 1 ct round brilliant before creating it
jewelry_gem_report(cut="round_brilliant", carat=1.0)
# → spread_mm=6.5, depth_mm=4.02, proportion_grade="Excellent"
# → colour_scale_hint="estimate — not a lab grade: GIA D–Z scale ..."
# → recommended_setting="prong (4 or 6 claw) solitaire"

# Check if an old European would fit a 5 mm seat
jewelry_gem_report(cut="old_european", diameter_mm=5.0)
# → spread_mm=5.0, table_pct=40.0, crown_angle_deg=40.0, proportion_grade="Very Good"

# Emerald cut step-cut clarity note
jewelry_gem_report(cut="emerald", diameter_mm=7.0)
# → clarity_hint includes "step cuts show inclusions more readily"
```

---

## Tool: `jewelry_gem_catalog` (read-only)

Birthstone and gem property catalog lookup.  Returns gem properties
for any gem by name or by birth month.  Does NOT write any file.

### Input

```
query : string (required) — gem name (e.g. "ruby") or birth month name
                            (e.g. "july", "April") or month number 1–12
```

### Output schema

```json
{
  "count": 1,
  "results": [
    {
      "gem": "ruby",
      "birth_months": [7],
      "mohs_hardness": 9.0,
      "refractive_index": [1.762, 1.770],
      "density_g_cm3": 3.99,
      "common_cuts": ["oval", "cushion", "round_brilliant", "pear", "emerald"],
      "colour_range": "Pinkish-red to deep red; finest are 'pigeon's blood' vivid red",
      "supported_cuts": ["oval", "cushion", "round_brilliant", "pear", "emerald"]
    }
  ]
}
```

`supported_cuts` = intersection of `common_cuts` with the current `GEMSTONE_CUTS`
registry (i.e. cuts that can be passed directly to `jewelry_create_gemstone`).

### Gem catalog at a glance

| Gem | Month(s) | Mohs | RI | Density (g/cm³) |
|-----|----------|------|----|-----------------|
| diamond | April (4) | 10 | 2.417–2.419 | 3.51 |
| ruby | July (7) | 9 | 1.762–1.770 | 3.99 |
| sapphire | September (9) | 9 | 1.762–1.770 | 4.00 |
| emerald | May (5) | 7.5–8 | 1.565–1.602 | 2.72 |
| amethyst | February (2) | 7 | 1.544–1.553 | 2.65 |
| aquamarine | March (3) | 7.5–8 | 1.567–1.590 | 2.72 |
| topaz | November (11) | 8 | 1.609–1.643 | 3.53 |
| garnet | January (1) | 6.5–7.5 | 1.714–1.888 | 3.78 |
| peridot | August (8) | 6.5–7 | 1.650–1.703 | 3.32 |
| citrine | November (11) | 7 | 1.544–1.553 | 2.65 |
| tanzanite | December (12) | 6–7 | 1.691–1.700 | 3.35 |
| opal | October (10) | 5.5–6.5 | 1.37–1.52 | 2.08 |
| pearl | June (6) | 2.5–4.5 | 1.53–1.685 | 2.71 |
| turquoise | December (12) | 5–6 | 1.610–1.650 | 2.75 |
| tourmaline | October (10) | 7–7.5 | 1.624–1.644 | 3.10 |
| spinel | August (8) | 8 | 1.712–1.762 | 3.60 |
| morganite | — (none) | 7.5–8 | 1.572–1.600 | 2.71 |
| alexandrite | June (6) | 8.5–9 | 1.746–1.755 | 3.73 |
| moonstone | June (6) | 6–6.5 | 1.518–1.526 | 2.56 |
| zircon | December (12) | 6–7.5 | 1.925–1.984 | 4.67 |

**Sources:** GIA Gem Reference Guide (Liddicoat, 1995), GIA Gemology Reference
(gia.edu/gems-gemology), GIA Gem Encyclopedia (2014 ed.),
Jewelers of America birthstone list (2016 revision),
American Gem Society (AGS) birthstone chart,
International Gem Society (IGS) gem property tables.

### Example

```
# All birthstones for July
jewelry_gem_catalog(query="july")
# → count=1, results=[{gem: "ruby", birth_months: [7], mohs: 9.0, ...}]

# All December birthstones
jewelry_gem_catalog(query="december")
# → count=3, results=[tanzanite, turquoise, zircon]

# Lookup by gem name
jewelry_gem_catalog(query="morganite")
# → density_g_cm3=2.71, mohs=7.5–8, common_cuts=[oval, cushion, ...]
```

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

## Worked example: 1 ct ruby oval solitaire (coloured stone)

```
# Ruby is denser than diamond (3.99 vs 3.51 g/cm³), so 1 ct ruby is
# physically smaller than a 1 ct diamond of the same cut.

jewelry_create_gemstone(
    file_id="<feature_file_uuid>",
    cut="oval",
    carat=1.0,
    material="ruby",       # triggers density correction automatically
    position=[0, 0, 5],
)
# → diameter_mm ≈ 7.39 mm (vs 7.70 mm for 1 ct diamond oval)

jewelry_cut_gem_seat(
    file_id="<feature_file_uuid>",
    cut="oval",
    carat=1.0,
    material="ruby",
    position=[0, 0, 5],
    auto_cut_host_id="sweep1-1"
)
```

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
- FeatureView dropdown does not yet list the 6 fancy cuts (radiant, asscher,
  trillion, heart, baguette, briolette), the 13 historical/specialty cuts
  (old_european, old_mine, rose_cut, single_cut, french_cut, half_moon,
  trapezoid, kite, bullet, tapered_baguette, lozenge, shield, calf_head),
  nor the 4 new step/mixed cuts (portuguese, ceylon, flanders, square_emerald).
  The Python spec + facet-family routing are complete for all 30 cuts; a
  consolidated frontend pass will add them to the UI dropdown enum.
  **Deferred: FeatureView UI — all 30 cuts need adding to the frontend cut-selector enum.**
- Setting styles (prong, bezel, channel, pavé) are not yet modelled — only
  the seat void is generated. The `recommended_setting` field in `jewelry_gem_report`
  is a text suggestion only; no geometry is generated for the setting style.
- The `colour_scale_hint` and `clarity_hint` fields in `jewelry_gem_report`
  are heuristic text placeholders — they are explicitly labelled "estimate —
  not a lab grade" and no optical or inclusion analysis is performed.
