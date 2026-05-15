# Jewelry: Gem-Seat Boolean — Advanced Seat Types

This document covers the full set of gem-seat tools in `kerf_cad_core.jewelry.gem_seat`.
For the basic `jewelry_cut_gem_seat` workflow and the original single-round-seat
algorithm, see also `jewelry_gemstones.md` (which documents the `gem_seat` node schema).

---

## Tool overview

| Tool | `op` node | Purpose |
|------|-----------|---------|
| `jewelry_cut_gem_seat` | `gem_seat` | Single seat — prong / flush / gypsy / any setting |
| `jewelry_cut_channel_seat` | `channel_seat` | Continuous groove for a row of N stones |
| `jewelry_cut_bezel_seat` | `bezel_seat` | Inner bore for bezel / collet setting |
| `jewelry_cut_fishtail_seat` | `fishtail_seat` | Small accent seat with bright-cut facet grooves |
| `jewelry_cut_multi_stone_seat` | `multi_stone_seat` | Graduated arrangement: center + side stones |

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

## Deferred / known limitations

- **FeatureView inspector**: none of the new seat op types (`channel_seat`,
  `bezel_seat`, `fishtail_seat`, `multi_stone_seat`) have inspector panels in
  `FeatureView.jsx` yet. Nodes are stored and the OCCT worker will receive them,
  but UI editing of their parameters is not wired up. Deferred.
- **OCCT worker ops**: `opChannelSeat`, `opBezealSeat`, `opFishtailSeat`,
  `opMultiStoneSeat` are not yet implemented in the worker. Nodes will show a
  "worker op not implemented" error in the evaluator. The pure-Python geometry
  math (groove dimensions, positions, clearances) is fully functional.
- Fancy-cut girdle profiles are computed and stored as geometry hints; the OCCT
  worker must interpret `girdle_profile.profile_shape` to extrude the correct
  non-circular bearing ledge.
