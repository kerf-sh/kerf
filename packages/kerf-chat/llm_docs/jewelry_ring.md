# jewelry_ring — Ring Shank & Size System

## Overview

Eleven LLM tools for jewelry ring-band CAD:

| Tool | Purpose |
|------|---------|
| `jewelry_ring_size_to_diameter` | Convert ring size ↔ inner diameter (mm) |
| `jewelry_create_ring_shank` | Append a `ring_shank` node to a `.feature` file |
| `jewelry_create_eternity_band` | Append an `eternity_band` node — full/half/three-quarter stone band |
| `jewelry_create_signet_ring` | Append a `signet_ring` node — engravable seal face + shank |
| `jewelry_create_stacking_band_set` | Append a `stacking_band_set` node — N thin stacking bands + optional wishbone |
| `jewelry_create_contoured_band` | Append a `contoured_band` node — curved/notched top to hug an engagement ring |
| `jewelry_create_solitaire_ring` | Append a `solitaire_ring` node — shank + centre-stone seat attach-point |
| `jewelry_create_mens_band` | Append a `mens_band` node — wide comfort/euro/bevel band + groove/milgrain/surface hints |
| `jewelry_create_wedding_set` | Append a `wedding_set` node — engagement ring + matched contoured band, paired |
| `jewelry_create_cocktail_ring` | Append a `cocktail_ring` node — tapered shank + large dome/cluster mount attach-point |
| `jewelry_create_bypass_ring` | Append a `bypass_ring` node — two-arm crossover / toi-et-moi with two stone attach-points |

---

## Ring-size systems

### US system

**Formula** (Hoover & Strong / industry standard):

```
inner_diameter_mm = 11.63 + 0.8128 × us_size
```

Source: Hoover & Strong ring-size reference; cross-checked against Stuller 2024
catalog and Town Talk published tables.

| US Size | Inner Diam (mm) | Circumference (mm) |
|---------|-----------------|-------------------|
| 0       | 11.63           | 36.5              |
| 3       | 14.07           | 44.2              |
| 5       | 15.69           | 49.3              |
| 6       | 16.50           | 51.8              |
| 7       | 17.32           | 54.4              |
| 8       | 18.14           | 57.0              |
| 9       | 18.95           | 59.5              |
| 10      | 19.76           | 62.1              |
| 13      | 22.20           | 69.7              |
| 16      | 24.65           | 77.4              |

Half-sizes accepted (7.5, "7½"). Valid range: 0–16.

### UK / AU system

Letter scale A–Z+3. Each letter maps to a specific circumference (mm) per the
British Standard / ISO 8653. Example values:

| UK/AU | Circumference (mm) | Approx. inner diam (mm) |
|-------|--------------------|------------------------|
| H     | 46.8               | 14.9                   |
| J     | 49.3               | 15.7                   |
| L     | 51.9               | 16.5                   |
| N     | 54.4               | 17.3                   |
| P     | 57.0               | 18.1                   |
| R     | 59.5               | 18.9                   |
| T     | 62.1               | 19.8                   |
| Z     | 69.7               | 22.2                   |
| Z+1   | 70.4               | 22.4                   |

Half-sizes: "N½", "P½", etc.

### EU system

EU size = inner circumference in mm (integer or half, range 41–76).

```
inner_diameter_mm = eu_size / π
```

### JP system

JIS B 4901 lookup table; integer sizes 1–30.

| JP | Circumference (mm) |
|----|-------------------|
| 1  | 38.1              |
| 7  | 43.5              |
| 13 | 48.8              |
| 17 | 52.4              |
| 23 | 57.7              |
| 30 | 64.0              |

---

## Sizing formula derivation

For any system, once inner diameter `d` is known:

```
inner_radius_mm     = d / 2
circumference_mm    = π × d
outer_diameter_mm   = d + 2 × thickness_mm
```

---

## Profile catalog

| Profile | Description |
|---------|-------------|
| `d_shape` | Flat outer face, curved inner bore — classic men's band |
| `comfort_fit` | Domed outer, rounded inner — slides on easily, most popular |
| `flat` | Fully flat top/bottom, square edges — modern/contemporary |
| `half_round` | Domed top, flat bottom — most common women's band |
| `knife_edge` | V-ridge along outer centre line — architectural/dramatic |
| `euro` | Square-ish with gently rounded corners — European standard |
| `tapered` | Width + thickness taper from shoulder to base; use with `taper_ratio` |
| `cigar_band` | Wide flat-top band with heavy bevelled edges — bold statement; use `cigar_bevel_ratio` (0 < v < 0.4, default 0.2) |
| `bombe` | Convex domed outer surface, flat inner bore — full rounded look; use `bombe_dome_ratio` (0 < v ≤ 1.0, default 0.5) |
| `concave` | Concave channel carved into the outer face — elegant groove detail; use `concave_depth_ratio` (0 < v < 0.5, default 0.3) |
| `square` | Square cross-section with sharp 90° corners — architectural/modern |
| `hammered` | Outer surface divided into flat hammer-strike facets — artisan texture; use `hammered_facet_count` (4–128, default 32) |
| `split_band` | Two parallel rail bands separated by a central gap — open split look; use `split_band_gap_mm` (> 0, default 1.0 mm) |

### Profile-specific hints (v2 profiles)

v2 profiles emit a `profile_hints` sub-object in the node for the occtWorker:

#### `cigar_band`
- `bevel_width_mm`: width of each bevel edge
- `flat_top_width_mm`: flat top face width

#### `bombe`
- `dome_height_mm`: outer dome height above base
- `dome_ratio`: fraction of half-width used for dome height

#### `concave`
- `channel_depth_mm`: depth of concave groove
- `channel_width_mm`: width of groove (60% of band_width)

#### `square`
- `corner_radius_mm`: always 0.0 (worker may add a micro-fillet for tooling)

#### `hammered`
- `facet_count`: number of flat facets around the circumference
- `facet_arc_deg`: arc span per facet (360 / facet_count)

#### `split_band`
- `gap_mm`: gap between the two rails
- `rail_width_mm`: each rail's width ((band_width − gap) / 2)

---

## Shoulder styles

The shoulder style describes how the shank meets the centre head or setting.

| Style | Description |
|-------|-------------|
| `plain` | Uniform band all the way around — no modification at top |
| `cathedral` | Arched shoulders that rise toward the setting; classic solitaire look |
| `split_shank` | Band splits into two prongs near the setting; dramatic open look |
| `bypass` | Two ends of the band pass alongside each other rather than meeting |

### Cathedral geometry hints

The `opRingShank` worker uses these hints from the node:

- `arch_height_mm`: how far the arch rises above the band top (≈ 35% of inner radius)
- `arch_start_deg`: degrees from the 12-o'clock position where the arch begins (default 70°)
- `blend_radius_mm`: fillet radius blending the arch to the shank

### Split-shank hints

- `split_start_deg`: angle from 12-o'clock where the split begins (default 55°)
- `prong_gap_mm`: gap between the two prongs
- `prong_width_mm`: each prong's width

### Bypass hints

- `bypass_offset_mm`: lateral offset of each end (default 60% of band width)
- `overlap_deg`: how many degrees the two ends overlap at the top (default 30°)

---

## v2 node-spec fields

### Band engraving (`engraving`)

Parametric engraving spec — **geometry hint only**; OCCT text rendering is
deferred to the occtWorker `opRingShank` implementation.

```json
{
  "engraving": {
    "text": "Always & Forever",
    "font_height_mm": 1.5,
    "depth_mm": 0.3,
    "position_deg": 180.0,
    "align": "centre"
  }
}
```

| Field | Default | Constraint |
|-------|---------|-----------|
| `text` | — | required; 1–200 chars |
| `font_height_mm` | 1.5 | > 0 mm |
| `depth_mm` | 0.3 | > 0 mm |
| `position_deg` | 180.0 | 0–360° (0 = bottom of band) |
| `align` | `"centre"` | `"centre"` / `"left"` / `"right"` |

### Sizing beads (`sizing_beads`)

Small hemispherical protrusions on the inner bore to create a snug fit
without resizing.

```json
{
  "sizing_beads": {
    "count": 2,
    "bead_diameter_mm": 1.0,
    "bead_height_mm": 0.4,
    "position_deg": 270.0
  }
}
```

| Field | Default | Constraint |
|-------|---------|-----------|
| `count` | 2 | 1–4 beads |
| `bead_diameter_mm` | 1.0 | > 0 mm |
| `bead_height_mm` | 0.4 | > 0 mm; must be < thickness / 4 |
| `position_deg` | 270.0 | 0–360° (first bead angular start) |

### Comfort-fit interior radius override (`comfort_fit_radius`)

Override the default interior dome radius (mm) for the `comfort_fit` profile.
If omitted, the occtWorker uses its default (≈ 0.8 × inner_radius).

```json
{ "comfort_fit_radius": 4.5 }
```

Constraint: > 0 mm.  Stored in node as `comfort_fit_radius_mm`.

### Finger-fit taper (`finger_fit_taper`)

Asymmetric taper angle (degrees) so the band is slightly wider on the knuckle
side, making it easier to slide over the knuckle while still fitting the finger.

```json
{ "finger_fit_taper": 5.0 }
```

Constraint: 0–15 degrees.  Stored as `finger_fit_taper_deg`.  0 = symmetric
(default); key is omitted from the node if value is 0.

### Width profile curve (`width_profile`)

An array of 2–10 floats describing the width taper from the shoulder (index 0)
to the back of the band (last index).  Each value is a ratio relative to
`band_width` — `1.0` = full width, `0.6` = 60% of `band_width`.

```json
{ "width_profile": [1.0, 0.90, 0.80, 0.75] }
```

Constraints:
- 2–10 elements
- Each value in range `(0, 1]`
- Omit for uniform width (no taper)

---

## Tool usage

### `jewelry_ring_size_to_diameter` — size conversion

**Forward** (size → diameter):

```json
{
  "system": "us",
  "size": 7
}
```

Response:
```json
{
  "system": "us",
  "size": 7,
  "inner_diameter_mm": 17.3196,
  "inner_radius_mm": 8.6598,
  "circumference_mm": 54.4388
}
```

**Inverse** (diameter → nearest size):

```json
{
  "system": "uk",
  "diameter_mm": 17.32
}
```

Response:
```json
{
  "system": "uk",
  "diameter_mm": 17.32,
  "nearest_size": "N",
  "nearest_size_diameter_mm": 17.3197
}
```

### `jewelry_create_ring_shank` — shank builder

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "band_width": 4.0,
  "thickness": 1.8,
  "profile": "comfort_fit",
  "shoulder_style": "cathedral"
}
```

Response:
```json
{
  "file_id": "<uuid>",
  "id": "ring_shank-1",
  "op": "ring_shank",
  "inner_diameter_mm": 17.3196,
  "outer_diameter_mm": 20.9196,
  "circumference_mm": 54.4388,
  "profile": "comfort_fit",
  "shoulder_style": "cathedral",
  "band_width_mm": 4.0,
  "thickness_mm": 1.8
}
```

**v2 example — hammered band with engraving, sizing beads and width taper:**

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "band_width": 5.0,
  "thickness": 2.0,
  "profile": "hammered",
  "hammered_facet_count": 24,
  "shoulder_style": "cathedral",
  "engraving": {
    "text": "Always & Forever",
    "font_height_mm": 1.5,
    "depth_mm": 0.3,
    "position_deg": 180.0,
    "align": "centre"
  },
  "sizing_beads": {
    "count": 2,
    "bead_diameter_mm": 1.0,
    "bead_height_mm": 0.35,
    "position_deg": 270.0
  },
  "comfort_fit_radius": 4.0,
  "finger_fit_taper": 3.0,
  "width_profile": [1.0, 0.9, 0.8]
}
```

---

## Worked example — US size 7 solitaire shank

1. Convert size: US 7 → 17.32 mm inner diameter, 54.44 mm circumference.
2. Choose profile `comfort_fit` (rounded inside for comfort).
3. Choose shoulder style `cathedral` (arched for a solitaire setting).
4. Band width 4 mm, thickness 1.8 mm → outer diameter 20.92 mm.
5. Cathedral arch height = 17.32/2 × 0.35 ≈ 3.03 mm above band top.
6. The `ring_shank-1` node is appended; the occtWorker evaluates it via
   `opRingShank`, sweeping the cross-section profile along a full 360° circle
   of radius 8.66 mm using a corrected Frenet frame, then applies the
   cathedral arch sweep on top.

---

## Validation rules

| Parameter | Constraint |
|-----------|-----------|
| system | us / uk / au / eu / jp |
| US size | 0–16 (half-sizes OK) |
| UK/AU size | A–Z+3 |
| EU size | 41–76 mm circumference |
| JP size | 1–30 (integer) |
| band_width | > 0 mm |
| thickness | > 0 mm |
| taper_ratio | > 0 |
| profile | see catalog above (13 profiles) |
| shoulder_style | plain / cathedral / split_shank / bypass |
| hammered_facet_count | 4–128 (default 32) |
| split_band_gap_mm | > 0; < band_width − 0.5 mm |
| bombe_dome_ratio | (0, 1.0] (default 0.5) |
| concave_depth_ratio | (0, 0.5) (default 0.3) |
| cigar_bevel_ratio | (0, 0.4) (default 0.2) |
| engraving.text | 1–200 chars |
| engraving.font_height_mm | > 0 mm (default 1.5) |
| engraving.depth_mm | > 0 mm (default 0.3) |
| engraving.position_deg | 0–360 (default 180) |
| engraving.align | centre / left / right |
| sizing_beads.count | 1–4 (default 2) |
| sizing_beads.bead_diameter_mm | > 0 mm (default 1.0) |
| sizing_beads.bead_height_mm | > 0 mm; < thickness / 4 (default 0.4) |
| sizing_beads.position_deg | 0–360 (default 270) |
| comfort_fit_radius | > 0 mm (optional override) |
| finger_fit_taper | 0–15 degrees (default 0 = symmetric) |
| width_profile | 2–10 floats, each in (0, 1] |

Error code `BAD_ARGS` is returned for all constraint violations.

---

## v3 Ring Types

### `jewelry_create_eternity_band` — eternity / anniversary band

Full-circle (or half / three-quarter) band set with equal stones around the circumference.
Stone count is auto-derived from ring circumference and stone pitch unless explicitly set.

**Node op**: `eternity_band`

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "stone_diameter_mm": 2.0,
  "coverage": "full",
  "setting_style": "channel",
  "thickness_mm": 1.2,
  "stone_spacing_mm": 0.1
}
```

**Response fields**: `stone_count`, `stone_count_auto`, `coverage_deg`, `arc_length_mm`,
`stone_pitch_mm`, `band_width_mm`, `setting_style`.

#### Coverage options

| `coverage` | Arc | Degrees |
|-----------|-----|---------|
| `full` | 360° (all around) | 360 |
| `three_quarter` | ¾ of the band | 270 |
| `half` | Top half only | 180 |

#### Setting styles

| `setting_style` | Description |
|----------------|-------------|
| `channel` | Stones sit in a channel cut between two metal rails |
| `shared_prong` | Adjacent stones share common prong claws |
| `pave` | Micro-pavé; stones packed close with minimal metal visibility |

#### Stone-count auto-derivation

```
arc_length = π × inner_diameter × coverage_fraction
pitch      = stone_diameter + stone_spacing
stone_count = round(arc_length / pitch)   # ≥ 1
```

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `stone_diameter_mm` | > 0 mm |
| `coverage` | full / half / three_quarter |
| `setting_style` | channel / shared_prong / pave |
| `band_width_mm` | ≥ stone_diameter_mm (auto = stone_diam + 0.6 mm) |
| `thickness_mm` | > 0 mm (default 1.2) |
| `stone_spacing_mm` | ≥ 0 mm (default 0.1) |
| `stone_count` | ≥ 1 if specified; else auto |

---

### `jewelry_create_signet_ring` — signet ring

Flat / oval / cushion engravable seal face fused to the ring shank. Intaglio/relief
engraving depth is a geometry hint for the occtWorker.

**Node op**: `signet_ring`

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "face_shape": "oval",
  "face_length_mm": 12.0,
  "face_width_mm": 10.0,
  "face_height_mm": 3.0,
  "intaglio_depth_mm": 0.5,
  "engraving": { "text": "WM", "depth_mm": 0.3 },
  "shoulder_style": "plain"
}
```

**Response fields**: `face_shape`, `face_length_mm`, `face_width_mm`, `face_height_mm`,
`face_area_mm2`, `intaglio_depth_mm`, `shoulder_hints`, optional `engraving`.

#### Face shapes

| `face_shape` | Description | Area formula |
|-------------|-------------|--------------|
| `flat` | Rectangle / flat plate | length × width |
| `oval` | Ellipse | π × (length/2) × (width/2) |
| `cushion` | Rounded square/rectangle | length × width × 0.9 |

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `face_shape` | flat / oval / cushion |
| `face_length_mm` | > 0 mm (default 12.0) |
| `face_width_mm` | > 0 mm (default 10.0) |
| `face_height_mm` | > 0 mm (default 3.0) |
| `intaglio_depth_mm` | ≥ 0; < face_height_mm (default 0) |
| `band_width_mm` | > 0 mm (default 4.0) |
| `thickness_mm` | > 0 mm (default 1.8) |
| `shoulder_style` | plain / cathedral / split_shank / bypass |
| `engraving` | same constraints as ring_shank engraving |

---

### `jewelry_create_stacking_band_set` — stacking / nesting set

Generates N thin stacking bands that sit side-by-side on the finger with a controlled
nest gap. Optionally includes a contour/wishbone band that nests against a solitaire.

**Node op**: `stacking_band_set`

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "band_count": 3,
  "band_width_mm": 2.0,
  "thickness_mm": 1.4,
  "profile": "flat",
  "nest_gap_mm": 0.1,
  "include_wishbone": true,
  "wishbone_notch_depth_mm": 0.8,
  "solitaire_node_id": "ring_shank-1"
}
```

**Response fields**: `band_count`, `band_width_mm`, `thickness_mm`, `total_span_mm`,
`bands` (array with per-band index, profile, offset_mm), `include_wishbone`,
optional `wishbone_notch_depth_mm`, `solitaire_node_id`, `per_band_profiles`.

#### Total span formula

```
pitch      = band_width + nest_gap
total_span = pitch × band_count − nest_gap
```

#### Valid stacking profiles

`flat`, `half_round`, `knife_edge`, `euro`, `comfort_fit`, `d_shape`,
`cigar_band`, `concave`.

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `band_count` | 1–8 (default 3) |
| `band_width_mm` | > 0 mm (default 2.0) |
| `thickness_mm` | > 0 mm (default 1.4) |
| `profile` | see valid stacking profiles above |
| `nest_gap_mm` | ≥ 0 mm (default 0.1) |
| `wishbone_notch_depth_mm` | > 0; < thickness_mm (required when include_wishbone=true) |
| `per_band_profiles` | list of band_count valid stacking profiles |

---

### `jewelry_create_contoured_band` — contoured / shadow band

A wedding / shadow band whose top profile is cut to hug the underside of an engagement ring.
`contour_style="curved"` produces a smooth concave arc; `"notched"` produces a V/U notch.

**Node op**: `contoured_band`

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "notch_depth_mm": 1.2,
  "notch_width_mm": 3.0,
  "match_radius_mm": 10.5,
  "contour_style": "curved",
  "band_width_mm": 3.5,
  "thickness_mm": 1.6,
  "profile": "flat",
  "shoulder_style": "plain",
  "engagement_ring_node_id": "ring_shank-1"
}
```

**Response fields**: `inner_diameter_mm`, `outer_diameter_mm`, `notch_depth_mm`,
`notch_width_mm`, `match_radius_mm`, `contour_style`, `contour_hints` (with
`notch_half_angle_deg` = arc half-angle of the notch at match radius),
`shoulder_hints`, optional `engagement_ring_node_id`.

#### Contour hints sub-object

```json
{
  "contour_hints": {
    "type": "curved",
    "notch_depth_mm": 1.2,
    "notch_width_mm": 3.0,
    "match_radius_mm": 10.5,
    "notch_half_angle_deg": 8.21
  }
}
```

`notch_half_angle_deg = asin(notch_width / 2 / match_radius)` — used by the
occtWorker to construct the concave cutter arc.

#### Matching an engagement ring

Set `match_radius_mm` = engagement ring `outer_diameter_mm / 2` for a perfect shadow fit.
Supply `engagement_ring_node_id` to let the occtWorker resolve the exact profile from
the referenced node.

#### Valid base profiles for contoured band

`flat`, `half_round`, `comfort_fit`, `d_shape`, `euro`.

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `notch_depth_mm` | > 0; < thickness_mm (default 1.2) |
| `notch_width_mm` | > 0; ≤ band_width_mm (default 3.0) |
| `match_radius_mm` | > 0 mm (default 10.5) |
| `contour_style` | curved / notched (default curved) |
| `band_width_mm` | > 0 mm (default 3.5) |
| `thickness_mm` | > 0 mm (default 1.6) |
| `profile` | see valid base profiles above |
| `shoulder_style` | plain / cathedral / split_shank / bypass |

---

## v4 Composite / Style Ring Builders

### Attach-point hint schema

All v4 builders emit an `attach_points` array in the feature node.  Each entry:

```json
{
  "type": "circular_seat",
  "position_deg": 0.0,
  "height_mm": 5.0,
  "diameter_mm": 6.5,
  "normal": [0, 0, 1]
}
```

Bypass-ring arms also carry `"arm": "A"|"B"` and `"lateral_offset_mm"`.
Cocktail ring also carries `"mount_style"` and `"mount_diameter_mm"`.
Toi-et-moi uses `"type": "toi_et_moi"` instead of `"circular_seat"`.

A downstream gem-seat or prong node resolves the full setting geometry from
these hints.  The `normal` is always `[0,0,1]` (shank-axis-aligned).

---

### `jewelry_create_solitaire_ring` — solitaire ring builder

Composite node: shank + a single centre-stone seat attach-point.

**Node op**: `solitaire_ring`
**Sub-ops**: `ring_shank` (shank sweep) + `setting_mount` (attach-point emission)

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "shank_profile": "comfort_fit",
  "shoulder_style": "cathedral",
  "band_width_mm": 3.0,
  "thickness_mm": 1.6,
  "head_height_mm": 5.0,
  "center_stone_diameter_mm": 6.5,
  "taper_ratio": 1.0
}
```

**Response fields**: `inner_diameter_mm`, `outer_diameter_mm`, `shank_profile`,
`shoulder_style`, `head_height_mm`, `center_stone_diameter_mm`, `attach_points`
(single circular_seat hint).

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `shank_profile` | any of the 13 profiles (see profile catalog) |
| `shoulder_style` | plain / cathedral / split_shank / bypass (default cathedral) |
| `band_width_mm` | > 0 mm (default 3.0) |
| `thickness_mm` | > 0 mm (default 1.6) |
| `head_height_mm` | > 0 mm (default 5.0) |
| `center_stone_diameter_mm` | > 0 mm (default 6.5 ≈ 1 ct round) |
| `taper_ratio` | (0, 1] (default 1.0 = uniform) |

---

### `jewelry_create_mens_band` — men's band builder

Wide comfort/euro/bevel-style band with optional centre groove, milgrain edges,
and surface-finish hint.

**Node op**: `mens_band`

```json
{
  "file_id": "<uuid>",
  "ring_size": 10,
  "system": "us",
  "profile": "comfort_fit",
  "band_width_mm": 8.0,
  "thickness_mm": 2.0,
  "groove_depth_mm": 0.5,
  "groove_width_mm": 2.0,
  "milgrain_edges": true,
  "milgrain_bead_diameter_mm": 0.5,
  "surface_finish": "matte"
}
```

**Response fields**: `inner_diameter_mm`, `outer_diameter_mm`, `profile`,
`band_width_mm`, `thickness_mm`, `surface_finish`.  When applicable:
`groove_hint` (type/depth/width), `milgrain_hint` (type/edges/bead_diameter_mm),
`surface_hint` (type + facet details for hammered).

#### Valid profiles for men's band

`comfort_fit`, `euro`, `d_shape`, `flat`, `cigar_band`, `bombe`, `concave`,
`square`, `half_round`.

#### Surface finish hints

| `surface_finish` | Description | Node emits |
|-----------------|-------------|------------|
| `polished` (default) | Mirror polish | no `surface_hint` key |
| `matte` | Flat diffuse finish | `{"type": "matte"}` |
| `satin` | Directional satin lines | `{"type": "satin"}` |
| `brushed` | Brushed metal texture | `{"type": "brushed"}` |
| `hammered` | Faceted hammer-strike | `{"type": "hammered", "facet_count": N, "facet_arc_deg": X}` |

#### Groove / inlay channel hint

When `groove_depth_mm > 0` the node includes:

```json
{
  "groove_hint": {
    "type": "centre_groove",
    "depth_mm": 0.5,
    "width_mm": 2.0,
    "position_deg": 0.0
  }
}
```

#### Milgrain edge hint

When `milgrain_edges=true`:

```json
{
  "milgrain_hint": {
    "type": "milgrain_edge",
    "bead_diameter_mm": 0.5,
    "edges": ["top", "bottom"]
  }
}
```

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `profile` | comfort_fit / euro / d_shape / flat / cigar_band / bombe / concave / square / half_round |
| `band_width_mm` | > 0 mm (default 8.0) |
| `thickness_mm` | > 0 mm (default 2.0) |
| `taper_ratio` | > 0 (default 1.0) |
| `groove_depth_mm` | ≥ 0; if > 0 must be < thickness / 2 (default 0) |
| `groove_width_mm` | > 0; < band_width_mm (required when groove_depth_mm > 0) |
| `milgrain_bead_diameter_mm` | > 0 (required when milgrain_edges=true, default 0.5) |
| `surface_finish` | polished / matte / hammered / satin / brushed |
| `hammered_facet_count` | 4–128 (default 32) |

---

### `jewelry_create_wedding_set` — engagement ring + matched contoured band

Composite node pairing an engagement ring shank with a matching contoured
wedding band.  The wedding band's `match_radius_mm` is auto-derived from the
engagement ring's outer radius so the two rings sit flush on the finger.

**Node op**: `wedding_set`
**Sub-ops**: `ring_shank` (engagement ring) + `contoured_band` (wedding band)

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "eng_profile": "comfort_fit",
  "eng_shoulder_style": "cathedral",
  "eng_band_width_mm": 2.5,
  "eng_thickness_mm": 1.6,
  "eng_taper_ratio": 1.0,
  "band_profile": "flat",
  "band_width_mm": 3.0,
  "band_thickness_mm": 1.6,
  "notch_depth_mm": 1.2,
  "notch_width_mm": 2.5,
  "contour_style": "curved"
}
```

**Response fields**: `inner_diameter_mm`, `match_radius_mm`, `composite_ops`,
node also carries `engagement_ring` sub-dict (op=`ring_shank`) and
`wedding_band` sub-dict (op=`contoured_band`, with `contour_hints` including
`notch_half_angle_deg`).

#### match_radius derivation

```
match_radius_mm = (inner_diameter_mm + 2 × eng_thickness_mm) / 2
```

The wedding band's `notch_half_angle_deg = asin(notch_width / 2 / match_radius)`.

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `eng_profile` | any of the 13 profiles |
| `eng_shoulder_style` | plain / cathedral / split_shank / bypass (default cathedral) |
| `eng_band_width_mm` | > 0 mm (default 2.5) |
| `eng_thickness_mm` | > 0 mm (default 1.6) |
| `eng_taper_ratio` | > 0 (default 1.0) |
| `band_profile` | flat / half_round / comfort_fit / d_shape / euro (default flat) |
| `band_width_mm` | > 0 mm (default 3.0) |
| `band_thickness_mm` | > 0 mm (default 1.6) |
| `notch_depth_mm` | > 0; < band_thickness_mm (default 1.2) |
| `notch_width_mm` | > 0; ≤ band_width_mm (default 2.5) |
| `contour_style` | curved / notched (default curved) |

---

### `jewelry_create_cocktail_ring` — cocktail / statement ring

Tapered shank + large dome/cluster/bezel/prong top-mount attach-point hint.

**Node op**: `cocktail_ring`
**Sub-ops**: `ring_shank` (tapered shank) + `mount_platform` (large top mount)

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "shank_profile": "tapered",
  "shoulder_style": "plain",
  "band_width_mm": 4.0,
  "thickness_mm": 1.8,
  "taper_ratio": 0.7,
  "mount_style": "dome",
  "mount_diameter_mm": 18.0,
  "mount_height_mm": 8.0,
  "stone_diameter_mm": 14.0
}
```

**Response fields**: `inner_diameter_mm`, `outer_diameter_mm`, `mount_style`,
`mount_diameter_mm`, `mount_height_mm`, `stone_diameter_mm`, `attach_points`
(single circular_seat hint with `mount_style` and `mount_diameter_mm`).

#### Mount styles

| `mount_style` | Description |
|--------------|-------------|
| `dome` | Solid convex dome platform |
| `cluster` | Multi-stone cluster platform |
| `bezel` | Bezel-set single large stone |
| `prong` | Prong-set large single stone |

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `shank_profile` | any of the 13 profiles (default tapered) |
| `shoulder_style` | plain / cathedral / split_shank / bypass (default plain) |
| `band_width_mm` | > 0 mm (default 4.0) |
| `thickness_mm` | > 0 mm (default 1.8) |
| `taper_ratio` | (0, 1] (default 0.7) |
| `mount_style` | dome / cluster / bezel / prong (default dome) |
| `mount_diameter_mm` | > 0 mm (default 18.0) |
| `mount_height_mm` | > 0 mm (default 8.0) |
| `stone_diameter_mm` | > 0; ≤ mount_diameter_mm (default 14.0) |

---

### `jewelry_create_bypass_ring` — bypass / crossover & toi-et-moi ring

Two-element shank with two stone mount attach-points.  Models both classic
crossover and toi-et-moi styles.

**Node op**: `bypass_ring`
**Sub-ops**: `bypass_arm_a`, `bypass_arm_b`

```json
{
  "file_id": "<uuid>",
  "ring_size": 7,
  "system": "us",
  "cross_style": "crossover",
  "profile": "half_round",
  "band_width_mm": 3.0,
  "thickness_mm": 1.5,
  "bypass_offset_mm": 4.0,
  "overlap_deg": 20.0,
  "stone_a_diameter_mm": 6.0,
  "stone_b_diameter_mm": 6.0,
  "mount_height_mm": 4.5
}
```

**Response fields**: `inner_diameter_mm`, `outer_diameter_mm`, `cross_style`,
`profile`, `bypass_offset_mm`, `stone_a_diameter_mm`, `stone_b_diameter_mm`,
`attach_points` (two entries, one per arm).

#### Attach-point detail for bypass

Each attach-point carries:
- `arm`: `"A"` or `"B"`
- `position_deg`: where the arm terminates (near the 12-o'clock position)
- `lateral_offset_mm`: arm A = +offset, arm B = −offset (lateral from centreline)
- `type`: `"circular_seat"` for crossover, `"toi_et_moi"` for toi-et-moi

#### Cross styles

| `cross_style` | Description |
|--------------|-------------|
| `crossover` | Arms visually intersect at 12-o'clock (offset in Z) |
| `toi_et_moi` | Two arms end side by side (two equal-prominence stones) |

#### Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `cross_style` | crossover / toi_et_moi (default crossover) |
| `profile` | any of the 13 profiles (default half_round) |
| `band_width_mm` | > 0 mm (default 3.0) |
| `thickness_mm` | > 0 mm (default 1.5) |
| `bypass_offset_mm` | > 0 mm (default 4.0) |
| `overlap_deg` | 0–90 degrees (default 20) |
| `stone_a_diameter_mm` | > 0 mm (default 6.0) |
| `stone_b_diameter_mm` | > 0 mm (default 6.0) |
| `mount_height_mm` | > 0 mm (default 4.5) |

---

## FeatureView note (deferred)

The five v4 composite ring types (`solitaire_ring`, `mens_band`, `wedding_set`,
`cocktail_ring`, `bypass_ring`) do not yet have dedicated FeatureView entries in
the front-end component (`src/components/`).  They render via the generic feature
node viewer until FeatureView cards are added.  This is deferred to a separate
front-end task.
