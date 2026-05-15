# Jewelry: Gem-Seat Boolean — Advanced Seat Types

This document covers the full set of gem-seat tools in `kerf_cad_core.jewelry.gem_seat`.
For the basic `jewelry_cut_gem_seat` workflow and the original single-round-seat
algorithm, see also `jewelry_gemstones.md` (which documents the `gem_seat` node schema).

---

## Tool overview

| Tool | `op` node | Purpose |
|------|-----------|---------|
| `jewelry_cut_gem_seat` | `gem_seat` | Single seat — prong / any setting |
| `jewelry_cut_channel_seat` | `channel_seat` | Continuous groove for a row of N stones (round bearing) |
| `jewelry_cut_bezel_seat` | `bezel_seat` | Inner bore for bezel / collet setting |
| `jewelry_cut_fishtail_seat` | `fishtail_seat` | Small accent seat with bright-cut facet grooves |
| `jewelry_cut_multi_stone_seat` | `multi_stone_seat` | Graduated arrangement: center + side stones |
| `jewelry_cut_pave_field_seat` | `pave_field_seat` | Grid/honeycomb of bearing seats for pavé fields |
| `jewelry_cut_cluster_halo_seat` | `cluster_halo_seat` | Ring of accent seats around a center stone (halo/cluster) |
| `jewelry_cut_gypsy_seat` | `gypsy_seat` | Flush/gypsy countersink seat (no bearing cone overhang) |
| `jewelry_cut_baguette_channel_seat` | `baguette_channel_seat` | Rectangular bearing groove for step-cut stones |

All tools accept `auto_cut_host_id` to immediately chain a `boolean` cut node
subtracting the seat from the named host solid — same pattern as the original tool.

---

## Fancy-cut girdle profiles

For non-round cuts the bearing ledge is not a circle.  `seat_geometry()` accepts an
optional `girdle_profile` dict produced by `fancy_cut_girdle_profile()`.

| Cut | `profile_shape` | Corner / blend |
|-----|----------------|----------------|
| `round_brilliant` | `circle` | 0 |
| `princess` | `square` | `corner_radius_mm` from `corner_radius_pct` |
| `oval` | `ellipse` | 0 |
| `marquise` | `stadium` | 0 (two semi-circles) |
| `pear` | `pear` | 0 |
| `emerald` | `rect_chamfer` | `corner_radius_mm` from `corner_cut_ratio` |
| `cushion` | `rect_chamfer` | `corner_radius_mm` from `corner_radius_pct` |

The `jewelry_cut_gem_seat` tool automatically computes and stores the girdle
profile for any non-round cut.  Override with `girdle_shape` to use a different
profile cut than the stone's nominal cut (e.g. seat sized to an oval but with
round proportions).

The `jewelry_cut_bezel_seat` tool also computes the fancy-cut girdle profile
automatically for non-round cuts.

---

## Channel seat

A single swept cutter that provides a bearing ledge for all N stones.

### Key constraints
- `pitch_mm` **must strictly exceed** `diameter_mm` (the stone's primary dimension).
  Violating this returns `BAD_ARGS`.

### `channel_seat` node schema

```json
{
  "id": "channel_seat-1",
  "op": "channel_seat",
  "cut": "round_brilliant",
  "n_stones": 5,
  "pitch_mm": 2.5,
  "stone_diameter_mm": 2.0,
  "stone_positions": [
    [0.0, 0.0, 0.0],
    [2.5, 0.0, 0.0],
    [5.0, 0.0, 0.0],
    [7.5, 0.0, 0.0],
    [10.0, 0.0, 0.0]
  ],
  "per_stone_geom": { /* same keys as gem_seat geometry */ },
  "groove_width_mm": 2.15,
  "groove_depth_mm": 1.72,
  "groove_length_mm": 12.15,
  "groove_wall_thickness_mm": 0.20,
  "total_cutter_depth_mm": 1.72
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `n_stones` | — | Required; integer ≥ 1 |
| `pitch_mm` | — | Required; must exceed `diameter_mm` |
| `position` | `[0,0,0]` | First stone centre |
| `axis_direction` | `[1,0,0]` | Row direction (normalised internally) |
| `groove_wall_thickness_mm` | 0.20 | Hint for OCCT worker; informational |
| Standard clearances | (see below) | Same as `jewelry_cut_gem_seat` |

---

## Bezel seat

A cylindrical (or tapered / collet) inner bore sized to the girdle.

### `bezel_seat` node schema

```json
{
  "id": "bezel_seat-1",
  "op": "bezel_seat",
  "cut": "oval",
  "seat_type": "bezel",
  "girdle_radius_mm": 4.08,
  "pavilion_depth_mm": 3.44,
  "bezel_wall_height_mm": 1.0,
  "tapered": false,
  "taper_angle_deg": 0.0,
  "inner_bore_top_radius": 4.08,
  "inner_bore_bottom_radius": 4.08,
  "total_cutter_depth_mm": 4.12,
  "girdle_profile": {
    "profile_shape": "ellipse",
    "long_axis_mm": 8.16,
    "short_axis_mm": 5.45,
    "corner_radius_mm": 0.0,
    "aspect_ratio": 0.66,
    "cut": "oval"
  }
  /* … plus all standard seat_geometry keys … */
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `bezel_wall_height_mm` | 1.0 | Collet wall height above girdle ledge |
| `tapered` | `false` | `true` = collet (tapered bore) |
| `taper_angle_deg` | 5.0 | Half-angle of tapered bore; only used if `tapered=true` |
| `girdle_clearance_mm` | 0.08 | Wider than prong default (metal pushed over) |
| `crown_relief_mm` | 0.20 | Shallower than prong default |

Fancy-cut girdle profile is computed automatically for all non-round cuts.

---

## Fishtail / bright-cut accent seat

Small round seat with radial bright-cut grooves for pavé and channel-pavé work.

### `fishtail_seat` node schema

```json
{
  "id": "fishtail_seat-1",
  "op": "fishtail_seat",
  "cut": "round_brilliant",
  "seat_type": "fishtail",
  "bright_cut_angle_deg": 45.0,
  "bright_cut_depth_mm": 0.15,
  "n_bright_facets": 4,
  "bright_cut_radius_mm": 1.43,
  "girdle_radius_mm": 1.28,
  "total_cutter_depth_mm": 1.35
  /* … plus all standard seat_geometry keys … */
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `bright_cut_angle_deg` | 45.0 | Half-angle of each groove from vertical |
| `bright_cut_depth_mm` | 0.15 | Axial depth of each groove |
| `n_bright_facets` | 4 | Count of radial grooves (typically 4 or 6) |
| `girdle_clearance_mm` | 0.04 | Tighter than prong (accent stones are snug) |
| `culet_clearance_mm` | 0.08 | |

`bright_cut_radius_mm = girdle_radius_mm + bright_cut_depth_mm × tan(bright_cut_angle_deg)`

---

## Multi-stone shared seat

Graduated arrangement with a single center stone flanked by symmetric side stones.

### Key constraints
- `n_side_stones` must be **even** (symmetric arrangement) and ≥ 2.
- `side_pitch_mm` must exceed `max(center_diameter_mm, side_diameter_mm)`.
  Violating either returns `BAD_ARGS`.

### `multi_stone_seat` node schema

```json
{
  "id": "multi_stone_seat-1",
  "op": "multi_stone_seat",
  "cut": "round_brilliant",
  "seat_type": "multi_stone",
  "center_seat_geom": { /* seat_geometry dict for center stone */ },
  "side_seat_geom":   { /* seat_geometry dict for side stones (all identical) */ },
  "center_position":  [0.0, 0.0, 0.0],
  "side_positions":   [[-7.5, 0.0, 0.0], [7.5, 0.0, 0.0]],
  "n_side_stones":    2,
  "side_pitch_mm":    7.5,
  "total_cutter_depth_mm": 4.02
}
```

### Parameters

| Parameter | Notes |
|-----------|-------|
| `center_carat` / `center_diameter_mm` | Size of center stone (one required) |
| `side_carat` / `side_diameter_mm` | Size of each side stone (one required) |
| `n_side_stones` | Even integer ≥ 2; default 2 (three-stone setting) |
| `side_pitch_mm` | Required; centre-to-centre between adjacent stones |
| `through_hole_center` | `true` = add through-hole to center seat only |

Side positions are symmetric about origin along ±X: `±pitch`, `±2×pitch`, etc.

---

## Standard clearance defaults

All seat tools share the same clearance parameters with the same defaults as
`jewelry_cut_gem_seat`, except where noted per-tool above.

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `girdle_clearance_mm` | 0.05 | Radial play so stone drops in |
| `culet_clearance_mm` | 0.10 | Tool room / light below pavilion |
| `seat_allowance_mm` | 0.02 | Axial bearing-ledge tolerance |
| `crown_relief_mm` | 0.30 | Countersink depth above girdle |

---

## Worked examples

### 5-stone channel band (round brilliants, 2 mm each)

```
jewelry_cut_channel_seat(
    file_id="<uuid>",
    cut="round_brilliant",
    diameter_mm=2.0,
    n_stones=5,
    pitch_mm=2.5,
    position=[0, 0, 0],
    axis_direction=[1, 0, 0],
    auto_cut_host_id="band-1"
)
# → channel_seat-1 (groove + 5 positions), boolean-1
```

### Oval bezel setting (8 mm oval, collet style)

```
jewelry_cut_bezel_seat(
    file_id="<uuid>",
    cut="oval",
    diameter_mm=8.0,
    bezel_wall_height_mm=1.2,
    tapered=True,
    taper_angle_deg=7.0,
    auto_cut_host_id="bezel-shell-1"
)
# → bezel_seat-1 with oval girdle_profile (ellipse), boolean-1
```

### Three-stone ring (1 ct center + two 0.3 ct sides)

```
jewelry_cut_multi_stone_seat(
    file_id="<uuid>",
    cut="round_brilliant",
    center_carat=1.0,      # → 6.5 mm diameter
    side_carat=0.3,        # → ~4.5 mm diameter
    n_side_stones=2,
    side_pitch_mm=7.5,     # must exceed 6.5 mm
    auto_cut_host_id="shank-1"
)
# → multi_stone_seat-1, boolean-1
# side_positions: [[-7.5, 0, 0], [7.5, 0, 0]]
```

### Pavé accent stones with bright-cut

```
jewelry_cut_fishtail_seat(
    file_id="<uuid>",
    cut="round_brilliant",
    diameter_mm=1.8,
    n_bright_facets=4,
    bright_cut_angle_deg=45.0,
    bright_cut_depth_mm=0.12,
    position=[3.0, 0, 0],
    auto_cut_host_id="shank-1"
)
# → fishtail_seat-1, boolean-1
```

---

---

## Bearing presets

All new seat tools (pavé field, halo, gypsy, baguette channel) accept an optional
`preset` parameter that controls clearance defaults.  Explicit clearance params always
override preset values.

| Preset | `girdle_clearance_mm` | `culet_clearance_mm` | `seat_allowance_mm` | `crown_relief_mm` |
|--------|-----------------------|----------------------|---------------------|-------------------|
| `tight` | 0.03 | 0.06 | 0.01 | 0.20 |
| `standard` | 0.05 | 0.10 | 0.02 | 0.30 |
| `deep` | 0.07 | 0.15 | 0.03 | 0.40 |

---

## Pavé-field seat

A rectangular region packed with small bearing seats in a regular grid or honeycomb pattern.

### Key constraints
- `field_width_mm` and `field_height_mm` must be positive.
- `arrangement` must be `"grid"` or `"honeycomb"`.
- If the field is too small for a single stone (considering `edge_margin_mm`), `n_stones=0`
  is returned — not an error.

### `pave_field_seat` node schema

```json
{
  "id": "pave_field_seat-1",
  "op": "pave_field_seat",
  "cut": "round_brilliant",
  "seat_type": "pave_field",
  "arrangement": "honeycomb",
  "stone_diameter_mm": 1.5,
  "per_seat_geom": { /* seat_geometry dict for a single seat */ },
  "stone_positions": [[x, y, 0.0], ...],
  "n_stones": 24,
  "field_width_mm": 10.0,
  "field_height_mm": 8.0,
  "pitch_x_mm": 1.8,
  "pitch_y_mm": 1.8,
  "min_spacing_mm": 0.30,
  "edge_margin_mm": 0.25,
  "total_cutter_depth_mm": 1.02
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `field_width_mm` | — | Required; X extent of the region |
| `field_height_mm` | — | Required; Y extent of the region |
| `arrangement` | `"grid"` | `"grid"` or `"honeycomb"` |
| `min_spacing_mm` | 0.30 | Metal between adjacent seat edges |
| `edge_margin_mm` | 0.25 | Clearance from field boundary to nearest seat edge |
| `preset` | `None` | Named clearance preset |

All stone positions have `z=0`; apply `position` to translate the whole field.

---

## Cluster / halo seat ring

A center stone seat at the origin surrounded by `n_accent` equally-spaced accent
seats at a given `halo_radius_mm`.

### Key constraints
- `n_accent` must be >= 3.
- `halo_radius_mm` must be positive.
- Center and accent stones can have different cuts.

### `cluster_halo_seat` node schema

```json
{
  "id": "cluster_halo_seat-1",
  "op": "cluster_halo_seat",
  "center_cut": "round_brilliant",
  "accent_cut": "round_brilliant",
  "seat_type": "cluster_halo",
  "n_accent": 8,
  "halo_radius_mm": 4.5,
  "center_seat_geom": { /* seat_geometry dict for center stone */ },
  "accent_seat_geom": { /* seat_geometry dict for accent stones (identical) */ },
  "center_position": [0.0, 0.0, 0.0],
  "accent_positions": [[x, y, 0.0], ...],
  "accent_angular_step_deg": 45.0,
  "start_angle_deg": 0.0,
  "total_cutter_depth_mm": 3.85
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `center_cut` | — | Required; cut of the center stone |
| `center_carat` / `center_diameter_mm` | — | One required |
| `accent_cut` | — | Required; cut of accent stones |
| `accent_carat` / `accent_diameter_mm` | — | One required |
| `n_accent` | — | Required; >= 3 |
| `halo_radius_mm` | — | Required; > 0 |
| `start_angle_deg` | 0.0 | Angular offset for first accent stone |
| `preset` | `None` | Named clearance preset |

---

## Gypsy / flush seat

A cylindrical bore flush with the metal surface.  No bearing-cone overhang above the
girdle; a countersink at the top admits the lower crown facets.

### `gypsy_seat` node schema

```json
{
  "id": "gypsy_seat-1",
  "op": "gypsy_seat",
  "cut": "round_brilliant",
  "seat_type": "gypsy",
  "countersink_angle_deg": 45.0,
  "countersink_depth_mm": 0.20,
  "countersink_top_radius": 3.47,
  "girdle_radius_mm": 3.27,
  "total_cutter_depth_mm": 3.38
  /* … plus all standard seat_geometry keys … */
}
```

`countersink_top_radius = girdle_radius_mm + countersink_depth_mm × tan(countersink_angle_deg)`

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `countersink_angle_deg` | 45.0 | Half-angle of the top countersink taper |
| `countersink_depth_mm` | 0.20 | Axial depth of the countersink |
| `girdle_clearance_mm` | 0.03 | Tighter than prong (flush fit) |
| `preset` | `None` | Named clearance preset |

---

## Baguette / trap channel seat (rectangular bearing)

A prismatic rectangular-section cutter for step-cut stones (baguette, trap, carré).
Unlike `channel_seat` (which uses a circular bearing cone), the wall profile is
straight — correct for rectangular girdles.  Stone dimensions are provided directly
(`length_mm`, `width_mm`, `pavilion_depth_mm`) rather than derived from cut proportions.

### Key constraints
- `pitch_mm` must strictly exceed `length_mm`.
- `length_mm`, `width_mm`, and `pavilion_depth_mm` must all be positive.

### `baguette_channel_seat` node schema

```json
{
  "id": "baguette_channel_seat-1",
  "op": "baguette_channel_seat",
  "cut": "baguette",
  "seat_type": "baguette_channel",
  "n_stones": 5,
  "pitch_mm": 4.5,
  "stone_length_mm": 4.0,
  "stone_width_mm": 2.0,
  "cutter_length_mm": 4.10,
  "cutter_width_mm": 2.10,
  "cutter_depth_mm": 1.02,
  "groove_length_mm": 22.10,
  "wall_thickness_mm": 0.20,
  "stone_positions": [[x, y, z], ...],
  "total_cutter_depth_mm": 1.02
}
```

### Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `length_mm` | — | Required; stone long-axis dimension |
| `width_mm` | — | Required; stone short-axis dimension |
| `pavilion_depth_mm` | — | Required; shallow for step-cuts (typically 0.5–1.5 mm) |
| `n_stones` | — | Required; >= 1 |
| `pitch_mm` | — | Required; must exceed `length_mm` |
| `wall_thickness_mm` | 0.20 | Metal wall hint for OCCT worker |
| `axis_direction` | `[1,0,0]` | Row direction (normalised internally) |
| `preset` | `None` | Named clearance preset |

---

## Worked examples (new seat types)

### Pavé field on a ring shank (1.5 mm round brilliants, honeycomb)

```
jewelry_cut_pave_field_seat(
    file_id="<uuid>",
    cut="round_brilliant",
    diameter_mm=1.5,
    field_width_mm=10.0,
    field_height_mm=4.0,
    arrangement="honeycomb",
    min_spacing_mm=0.30,
    preset="tight",
    auto_cut_host_id="shank-1"
)
# → pave_field_seat-1 (positions + per-seat geom), boolean-1
```

### 1 ct halo ring (8 × 1.5 mm accent stones, 4.5 mm radius)

```
jewelry_cut_cluster_halo_seat(
    file_id="<uuid>",
    center_cut="round_brilliant",
    center_carat=1.0,      # → 6.5 mm
    accent_cut="round_brilliant",
    accent_diameter_mm=1.5,
    n_accent=8,
    halo_radius_mm=4.5,
    auto_cut_host_id="bezel-1"
)
# → cluster_halo_seat-1 (center + 8 accent positions), boolean-1
```

### Gypsy-set 6.5 mm round brilliant

```
jewelry_cut_gypsy_seat(
    file_id="<uuid>",
    cut="round_brilliant",
    carat=1.0,
    countersink_angle_deg=45.0,
    countersink_depth_mm=0.20,
    preset="tight",
    auto_cut_host_id="band-1"
)
# → gypsy_seat-1, boolean-1
```

### Baguette channel (five 4×2 mm baguettes)

```
jewelry_cut_baguette_channel_seat(
    file_id="<uuid>",
    cut="baguette",
    length_mm=4.0,
    width_mm=2.0,
    pavilion_depth_mm=0.8,
    n_stones=5,
    pitch_mm=4.5,
    auto_cut_host_id="eternity-1"
)
# → baguette_channel_seat-1 (5 positions), boolean-1
```

---

## Deferred / known limitations

- **FeatureView inspector**: none of the seat op types (`channel_seat`,
  `bezel_seat`, `fishtail_seat`, `multi_stone_seat`, `pave_field_seat`,
  `cluster_halo_seat`, `gypsy_seat`, `baguette_channel_seat`) have inspector
  panels in `FeatureView.jsx` yet. Nodes are stored and the OCCT worker will
  receive them, but UI editing of their parameters is not wired up. Deferred.
- **OCCT worker ops**: `opPaveFieldSeat`, `opClusterHaloSeat`, `opGypsySeat`,
  `opBaguetteChannelSeat` (and the earlier `opChannelSeat`, `opBezealSeat`,
  `opFishtailSeat`, `opMultiStoneSeat`) are not yet implemented in the worker.
  Nodes will show a "worker op not implemented" error in the evaluator.
  The pure-Python geometry math (positions, clearances, dimensions) is fully
  functional and tested.
- Fancy-cut girdle profiles are computed and stored as geometry hints; the OCCT
  worker must interpret `girdle_profile.profile_shape` to extrude the correct
  non-circular bearing ledge.
