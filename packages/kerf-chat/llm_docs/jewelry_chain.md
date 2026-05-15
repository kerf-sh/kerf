# jewelry_chain — Parametric Chain, Bracelet & Necklace Builder

## Overview

Two LLM tools for parametric chain CAD:

| Tool | Write? | Purpose |
|------|--------|---------|
| `jewelry_create_chain` | yes | Append a `chain_assembly` node to a `.feature` file |
| `jewelry_chain_length` | no  | Convert between chain length and link count (helper) |

---

## Link styles

### Original styles

| Style | Description |
|-------|-------------|
| `cable` | Alternating round-wire ovals, every other link rotated 90° — the classic all-purpose chain |
| `curb` | Twisted links lying flat; set `diamond_cut=true` for faceted finish, `flat=true` for flattened wire |
| `figaro` | Repeating pattern of (by default) 3 short links + 1 elongated link; `long_link_ratio` controls the elongation |
| `rope` | Small oval links twisted into a continuous helical spiral; `twist_angle_deg` controls the helix pitch |
| `box` | Square hollow tube links joined end-to-end; clean, architectural look |
| `snake` | Wide flat scalloped elements on a fine box core |
| `byzantine` | Complex 4-link cluster weave — historically rich, dense pattern |
| `mariner` | Oval links each with a perpendicular central stabiliser bar — anchor chain profile |

### v2 styles

| Style | Description | Key hint fields |
|-------|-------------|-----------------|
| `rolo` | Round/belcher: wide round links with ~1:1 aspect, alternating 90° rotation | `inner_diameter_mm`, `aspect_ratio` |
| `bismark` | Multi-row parallel interlocked oval links; use `rows=` for row count (default 2) | `rows`, `row_spacing_mm` |
| `wheat` | Spiga: figure-8 links twisted into a helical spiral — rope-like appearance | `figure8_ratio`, `helix_radius_mult` |
| `herringbone` | Flat V-shaped woven surface; no visible individual links; very wide | `surface_width_mm`, `v_angle_deg`, `layer_count` |
| `omega` | Solid curved plates on a fine box/fabric core spine — wide flat collar look | `plate_width_mm`, `plate_curvature` |
| `popcorn` | Bumpy spheroidal bead-like links — textured, chunky | `sphere_diameter_mm`, `neck_diameter_mm` |
| `ball` | Smooth spherical beads connected by short cylindrical necks (bead chain) | `bead_diameter_mm`, `neck_diameter_mm`, `neck_length_mm` |
| `singapore` | Twisted curb: figure-8 links rotated 90° — diagonal light reflection | `twist_deg`, `diagonal_angle_deg` |

### Style aliases

| Alias | Resolves to |
|-------|-------------|
| `anchor` | `mariner` |
| `belcher` | `rolo` |
| `spiga` | `wheat` |
| `bead` | `ball` |
| `bead_chain` | `ball` |
| `diamond_cut_curb` | `curb` (use `diamond_cut=true`) |

---

## Clasps

| Style | Description |
|-------|-------------|
| `lobster` | Lobster-claw spring gate on a swivel — most common jewellery clasp |
| `spring_ring` | Circular spring-loaded ring gate |
| `toggle` | T-bar + ring toggle — decorative, easy-open |
| `box_clasp` | Rectangular box with a spring tab — secure, flat profile |

Attach a clasp inline by passing `clasp_style` to `jewelry_create_chain`.

---

## Standard chain lengths

Use as the `standard_length` parameter:

### Anklets

| Name | Length |
|------|--------|
| `anklet_9in`    | 228.6 mm |
| `anklet_9.5in`  | 241.3 mm |
| `anklet_10in`   | 254.0 mm |
| `anklet_10.5in` | 266.7 mm |
| `anklet_11in`   | 279.4 mm |

### Bracelets

| Name | Length |
|------|--------|
| `bracelet_6.5in` | 165.1 mm |
| `bracelet_7in`   | 177.8 mm |
| `bracelet_7.5in` | 190.5 mm |
| `bracelet_8in`   | 203.2 mm |
| `bracelet_18cm`  | 180.0 mm |
| `bracelet_19cm`  | 190.0 mm |
| `bracelet_20cm`  | 200.0 mm |

### Chokers

| Name | Length |
|------|--------|
| `choker_14in` | 355.6 mm |
| `choker_16in` | 406.4 mm |

### Necklaces

| Name | Length |
|------|--------|
| `collar_14in`   | 355.6 mm |
| `collar_16in`   | 406.4 mm |
| `princess_18in` | 457.2 mm |
| `matinee_20in`  | 508.0 mm |
| `matinee_22in`  | 558.8 mm |
| `opera_24in`    | 609.6 mm |
| `opera_28in`    | 711.2 mm |
| `rope_30in`     | 762.0 mm |
| `rope_36in`     | 914.4 mm |
| `necklace_40cm` | 400.0 mm |
| `necklace_45cm` | 450.0 mm |
| `necklace_50cm` | 500.0 mm |
| `necklace_55cm` | 550.0 mm |
| `necklace_60cm` | 600.0 mm |
| `necklace_70cm` | 700.0 mm |
| `necklace_75cm` | 750.0 mm |

### Men's chain lengths

| Name | Length |
|------|--------|
| `mens_20in` | 508.0 mm |
| `mens_22in` | 558.8 mm |
| `mens_24in` | 609.6 mm |
| `mens_26in` | 660.4 mm |
| `mens_28in` | 711.2 mm |
| `mens_30in` | 762.0 mm |

---

## Link geometry defaults

When `link_length_mm` and `link_width_mm` are omitted, defaults are
derived from `wire_gauge_mm`:

| Style | link_length = gauge × | link_width = gauge × |
|-------|----------------------|---------------------|
| cable | 3.5 | 2.5 |
| curb | 3.0 | 2.5 |
| figaro | 3.5 | 2.5 |
| rope | 2.5 | 2.0 |
| box | 2.0 | 2.0 |
| snake | 2.2 | 2.8 |
| byzantine | 3.8 | 2.5 |
| mariner | 4.0 | 2.8 |
| rolo | 2.5 | 2.5 |
| bismark | 3.2 | 4.0 |
| wheat | 3.0 | 2.2 |
| herringbone | 1.5 | 3.5 |
| omega | 1.8 | 4.5 |
| popcorn | 3.0 | 3.0 |
| ball | 2.8 | 2.8 |
| singapore | 3.0 | 2.5 |

---

## Chain-length ↔ link-count math

Link pitch = the centre-to-centre chain advance per link:

- Most interlocking styles: `pitch ≈ link_length − 2 × wire_gauge`
- Box / snake / omega: `pitch ≈ link_length / 2` (side-by-side overlap)
- Byzantine: `pitch ≈ (link_length − 2 × gauge) × 0.7` (compact weave)
- Rope / wheat (spiga): `pitch ≈ (link_length − 2 × gauge) × 0.5` (tight helix)
- Herringbone: `pitch ≈ link_length × 0.4` (near-continuous surface)
- Bismark: `pitch ≈ (link_length − 2 × gauge) × 0.8` (slightly compact multi-row)
- Ball / popcorn: `pitch ≈ link_length` (bead centre-to-centre)

```
link_count  = round(total_length_mm / pitch_mm)
total_length_mm = link_count × pitch_mm
```

Use `jewelry_chain_length` to compute these without writing to a file.

---

## Gauge presets

Use `gauge_preset` instead of `wire_gauge_mm` to quickly select fine / medium / heavy
weight. Typical values (mm):

| Style | fine | medium | heavy |
|-------|------|--------|-------|
| cable | 0.7 | 1.0 | 1.5 |
| curb | 0.8 | 1.2 | 1.8 |
| figaro | 0.8 | 1.1 | 1.6 |
| rope | 0.6 | 0.9 | 1.3 |
| box | 0.8 | 1.2 | 1.8 |
| snake | 0.9 | 1.4 | 2.0 |
| byzantine | 0.7 | 1.0 | 1.4 |
| mariner | 1.0 | 1.5 | 2.2 |
| rolo | 1.0 | 1.5 | 2.2 |
| bismark | 0.9 | 1.3 | 1.9 |
| wheat | 0.7 | 1.0 | 1.5 |
| herringbone | 1.0 | 1.5 | 2.2 |
| omega | 1.2 | 1.8 | 2.5 |
| popcorn | 1.0 | 1.5 | 2.0 |
| ball | 1.0 | 1.5 | 2.5 |
| singapore | 0.8 | 1.1 | 1.6 |

Example: `"gauge_preset": "heavy"` on a `mariner` chain sets `wire_gauge_mm = 2.2`.

---

## Metal weight estimate

`chain_weight_estimate(style, wire_gauge_mm, total_length_mm, density_g_per_cm3)`
returns an approximate chain mass in grams.

**Formula**:
```
wire_area_mm2 = π × (wire_gauge_mm / 2)²
volume_mm3    = wire_area_mm2 × fill_factor × total_length_mm
mass_g        = volume_mm3 × density_g_per_cm3 × 1e-3
```

`fill_factor` is an empirical per-style constant (0–1) representing the fraction of
the chain's swept volume that is solid metal.  Dense styles like bismark (0.80) and
herringbone (0.85) have high fill factors; hollow styles like box (0.40) have lower ones.

**Common metal densities** (g/cm³):

| Metal | Density |
|-------|---------|
| 18k yellow gold | 15.5 |
| 14k yellow gold | 13.0 |
| 14k white gold | 13.0 |
| 18k white gold | 14.7 |
| Sterling silver 925 | 10.3 |
| Platinum 950 | 20.7 |
| Titanium | 4.5 |

This is a Python helper function — it does **not** write to a file or call any LLM tool.
Pass `fill_factor=` to override the style default for custom constructions.

---

## Graduated chains

Set `graduated=true` to request that the worker scale links linearly from the centre
outward toward the clasp ends (smaller links at the sides, larger at the centre).
The hint is stored as `"graduated": true` in the node spec.

---

---

## Node-spec schema (`chain_assembly`)

The appended feature node has this shape:

```json
{
  "id": "chain_assembly-1",
  "op": "chain_assembly",
  "style": "cable",

  "wire_gauge_mm": 1.0,
  "link_length_mm": 3.5,
  "link_width_mm": 2.5,
  "link_count": 71,

  "link_hints": {
    "type": "cable",
    "aspect_ratio": 1.4,
    "cross_section": "round",
    "alternating_rotation_deg": 90
  },

  "total_length_mm": 177.8,
  "link_pitch_mm": 2.5,
  "open_ends": true,

  "clasp": {
    "op": "clasp",
    "style": "lobster",
    "wire_gauge_mm": 1.0,
    "clasp_hints": {
      "type": "lobster",
      "body_length_mm": 6.0,
      "body_width_mm": 3.5,
      "spring_type": "lobster_claw_spring",
      "gate_type": "swivel"
    }
  }
}
```

The `clasp` key is `null` when no clasp is requested.

The occtWorker's `opChainAssembly` consumes the `link_hints` dict and the top-level
geometry parameters to build the repeating link geometry and overall assembly.

---

## Tool usage

### `jewelry_create_chain` — build a chain feature node

**Minimal example — 7-inch bracelet in cable style:**

```json
{
  "file_id": "<uuid>",
  "style": "cable",
  "wire_gauge_mm": 1.0,
  "standard_length": "bracelet_7in"
}
```

Response:
```json
{
  "file_id": "<uuid>",
  "id": "chain_assembly-1",
  "op": "chain_assembly",
  "style": "cable",
  "wire_gauge_mm": 1.0,
  "link_count": 71,
  "total_length_mm": 177.75,
  "link_pitch_mm": 2.5,
  "clasp": null
}
```

**With clasp:**

```json
{
  "file_id": "<uuid>",
  "style": "cable",
  "wire_gauge_mm": 1.0,
  "standard_length": "bracelet_7in",
  "clasp_style": "lobster"
}
```

**Curb chain, diamond-cut, princess-length necklace:**

```json
{
  "file_id": "<uuid>",
  "style": "curb",
  "wire_gauge_mm": 1.5,
  "standard_length": "princess_18in",
  "diamond_cut": true
}
```

**Byzantine with explicit link count:**

```json
{
  "file_id": "<uuid>",
  "style": "byzantine",
  "wire_gauge_mm": 0.9,
  "link_count": 80
}
```

**Rolo anklet, medium gauge:**

```json
{
  "file_id": "<uuid>",
  "style": "rolo",
  "gauge_preset": "medium",
  "standard_length": "anklet_10in"
}
```

**Bismark necklace, 3 rows, men's 24-inch:**

```json
{
  "file_id": "<uuid>",
  "style": "bismark",
  "wire_gauge_mm": 1.3,
  "rows": 3,
  "standard_length": "mens_24in"
}
```

**Graduated herringbone necklace:**

```json
{
  "file_id": "<uuid>",
  "style": "herringbone",
  "wire_gauge_mm": 1.5,
  "standard_length": "princess_18in",
  "graduated": true
}
```

---

### `jewelry_chain_length` — read-only length helper

**Standard length → link count:**

```json
{
  "style": "curb",
  "wire_gauge_mm": 1.2,
  "standard_length": "princess_18in"
}
```

Response:
```json
{
  "style": "curb",
  "wire_gauge_mm": 1.2,
  "link_length_mm": 3.6,
  "link_width_mm": 3.0,
  "link_pitch_mm": 1.32,
  "requested_length_mm": 457.2,
  "link_count": 346,
  "actual_total_length_mm": 456.72,
  "standard_length": "princess_18in"
}
```

**Link count → total length:**

```json
{
  "style": "cable",
  "wire_gauge_mm": 1.0,
  "link_count": 100
}
```

---

## Validation rules

| Parameter | Constraint |
|-----------|-----------|
| `style` | One of the 16 valid styles or an alias; see tables above |
| `wire_gauge_mm` | > 0 mm; ≤ 20 mm |
| `gauge_preset` | `"fine"`, `"medium"`, or `"heavy"`; overrides `wire_gauge_mm` |
| `link_length_mm` | > 0 mm; ≥ wire_gauge_mm |
| `link_width_mm` | > 0 mm; ≥ wire_gauge_mm |
| `link_count` | Positive integer ≥ 1 |
| `total_length_mm` | > 0 mm |
| `standard_length` | Must be a key in the standard-lengths table |
| Length source | Exactly one of `link_count`, `total_length_mm`, `standard_length` |
| `clasp_style` | One of: lobster, spring_ring, toggle, box_clasp |
| `long_link_ratio` | Figaro only; > 0 |
| `twist_angle_deg` | Rope/wheat only; degrees |
| `rows` | Bismark only; positive integer ≥ 1 (default 2) |
| `graduated` | Boolean; default false |

Error code `BAD_ARGS` is returned for all constraint violations.  
Error code `NOT_FOUND` is returned when the target file does not exist or is not a feature file.

---

## Worked example — 18-inch rope necklace with spring-ring clasp

1. Choose style `rope`, `wire_gauge_mm=0.8`, standard length `princess_18in`.
2. Default link dimensions: length = 0.8 × 2.5 = 2.0 mm, width = 0.8 × 2.0 = 1.6 mm.
3. Rope pitch = (2.0 − 2×0.8) × 0.5 = 0.2 mm (very dense helix).
   → link_count ≈ 457.2 / 0.2 = 2286 links.
4. Attach `spring_ring` clasp inline.

```json
{
  "file_id": "<uuid>",
  "style": "rope",
  "wire_gauge_mm": 0.8,
  "standard_length": "princess_18in",
  "clasp_style": "spring_ring"
}
```

The `chain_assembly-1` node is appended to the feature file.  The
`opChainAssembly` worker reads `link_hints.twist_angle_deg = 45` and
`link_hints.helix_radius_mult = 0.55` to build the continuous helical
twist geometry.

---

## FeatureView inspector

*(Deferred to a future consolidated frontend pass — the `chain_assembly`
op is not yet wired into `FeatureView.jsx`.  The feature node is stored
and can be evaluated by the worker immediately; only the inspector panel
UI is pending.  This applies equally to the v3 composed piece ops below.)*

---

## v3 — Composed chain pieces

Six higher-level builders that compose existing `chain_assembly` link hints.
Each produces a node with `op` set to the piece type; the node carries a
`chains` list of full `chain_assembly` sub-specs (consumed as
`opChainAssembly` calls by the worker) plus piece-specific hint dicts.

| Tool | Write? | Piece |
|------|--------|-------|
| `jewelry_create_tennis_bracelet` | yes | Continuous stone line in flexible link mounts |
| `jewelry_create_station_necklace` | yes | Periodic stone stations on a carrier chain |
| `jewelry_create_lariat` | yes | Open-ended Y-necklace with drop slide |
| `jewelry_create_charm_bracelet` | yes | Base chain + N jump-ring attach points |
| `jewelry_create_multi_strand` | yes | 2–5 parallel chains joined at connector + clasp |
| `jewelry_create_extender_chain` | yes | Adjustable extender with end loops |

All composed tools require only `file_id` as a mandatory parameter; everything
else has sensible defaults.

---

### `jewelry_create_tennis_bracelet`

A continuous line of equal round stones set in flexible link mounts.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `stone_size_mm` | number | 3.0 | Round stone diameter mm |
| `stone_count` | integer | — | Mutually exclusive with `total_length_mm` / `standard_length` |
| `total_length_mm` | number | — | Bracelet length; derives stone_count |
| `standard_length` | string | — | Named standard length key |
| `link_style` | string | `"cable"` | Any valid link style |
| `wire_gauge_mm` | number | 0.8 | |
| `clasp_style` | string | `"box_clasp"` | Flat profile suits tennis |
| `gauge_preset` | string | — | `"fine"` / `"medium"` / `"heavy"` |

Node keys: `op`, `stone_size_mm`, `stone_count`, `total_length_mm`,
`stone_pitch_mm`, `stone_station_hints`, `chains`, `clasp`,
`estimated_weight_18k_gold_g`.

`stone_station_hints.station_type = "tennis_mount"`, `prong_count = 4`.

**Example:**
```json
{"file_id": "<uuid>", "stone_size_mm": 3.0, "standard_length": "bracelet_7in",
 "clasp_style": "box_clasp"}
```

---

### `jewelry_create_station_necklace`

Periodic stone stations spaced along a thin carrier chain.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `stone_size_mm` | number | 4.0 | |
| `station_count` | integer | 5 | Number of stone stations |
| `station_spacing_mm` | number | 50.0 | Centre-to-centre spacing mm |
| `carrier_style` | string | `"cable"` | Any valid link style |
| `wire_gauge_mm` | number | 0.7 | |
| `clasp_style` | string | `"lobster"` | |
| `total_length_mm` | number | — | Override length; spacing preserved |
| `standard_length` | string | — | Named standard length key |
| `gauge_preset` | string | — | |

Node keys: `op`, `stone_size_mm`, `station_count`, `station_spacing_mm`,
`total_length_mm`, `station_hints`, `chains`, `clasp`,
`estimated_weight_18k_gold_g`.

`station_hints.station_positions = "evenly_spaced"`.

**Example:**
```json
{"file_id": "<uuid>", "station_count": 7, "station_spacing_mm": 55.0,
 "standard_length": "opera_24in"}
```

---

### `jewelry_create_lariat`

Open-ended Y-necklace with a sliding drop pendant.  No clasp (`clasp: null`).
Emits two `chain_assembly` sub-specs: body + drop.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `body_length_mm` | number | 400.0 | Main body chain mm |
| `drop_length_mm` | number | 80.0 | Drop/tail chain mm |
| `body_style` | string | `"cable"` | |
| `drop_style` | string | body_style | Defaults to same as body |
| `wire_gauge_mm` | number | 0.8 | Shared by body and drop |
| `slide_type` | string | `"loop_slide"` | `"loop_slide"` or `"bail_slide"` |
| `terminal_stone_mm` | number | 5.0 | Drop-end stone diameter mm |
| `gauge_preset` | string | — | |

Node keys: `op`, `body_length_mm`, `drop_length_mm`, `slide_type`,
`terminal_stone_mm`, `slide_hints`, `terminal_hints`, `chains` (2 entries),
`clasp` (null), `estimated_weight_18k_gold_g`.

**Example:**
```json
{"file_id": "<uuid>", "body_length_mm": 450.0, "drop_length_mm": 100.0,
 "body_style": "cable", "drop_style": "box"}
```

---

### `jewelry_create_charm_bracelet`

Base chain with N evenly-spaced jump-ring attach points for charms.
Rolo / belcher links are the traditional choice.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `base_style` | string | `"rolo"` | |
| `wire_gauge_mm` | number | 1.2 | |
| `total_length_mm` | number | — | Mutually exclusive with `link_count` / `standard_length` |
| `standard_length` | string | — | |
| `link_count` | integer | — | |
| `charm_count` | integer | 8 | Number of attach points |
| `clasp_style` | string | `"lobster"` | |
| `jump_ring_gauge_mm` | number | wire_gauge × 0.7 | |
| `gauge_preset` | string | — | |

Node keys: `op`, `charm_count`, `total_length_mm`, `attach_hints`, `chains`,
`clasp`, `estimated_weight_18k_gold_g`.

`attach_hints.positions_mm` — list of mm positions along the bracelet.

**Example:**
```json
{"file_id": "<uuid>", "standard_length": "bracelet_7in", "charm_count": 10,
 "base_style": "rolo"}
```

---

### `jewelry_create_multi_strand`

Two to five parallel chains joined at a connector and clasp.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `strand_count` | integer | 3 | 2–5 |
| `strand_styles` | array | all `"cable"` | Per-strand styles; padded to strand_count |
| `wire_gauge_mm` | number | 0.8 | Shared by all strands |
| `total_length_mm` | number | — | Per-strand length |
| `standard_length` | string | — | |
| `link_count` | integer | — | Per-strand link count |
| `clasp_style` | string | `"box_clasp"` | Multi-tab suits multi-strand |
| `connector_type` | string | `"multi_strand_box"` | `"multi_strand_box"` or `"end_bar"` |
| `gauge_preset` | string | — | |

Node keys: `op`, `strand_count`, `strand_styles`, `total_length_mm`,
`connector_hints`, `chains` (N entries), `clasp`,
`estimated_weight_18k_gold_g`.

**Example:**
```json
{"file_id": "<uuid>", "strand_count": 3,
 "strand_styles": ["cable", "rope", "cable"],
 "standard_length": "princess_18in"}
```

---

### `jewelry_create_extender_chain`

A short chain with a series of end loops for adjustable length attachment.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `extender_style` | string | `"cable"` | |
| `wire_gauge_mm` | number | 0.7 | |
| `extender_length_mm` | number | 50.0 | Total extender length mm |
| `loop_count` | integer | 5 | Number of attachment loops |
| `loop_spacing_mm` | number | length/(loop_count+1) | Spacing between loops mm |
| `end_ring_style` | string | `"lobster"` | Clasp at extender end |
| `gauge_preset` | string | — | |

Node keys: `op`, `extender_length_mm`, `loop_count`, `loop_spacing_mm`,
`loop_hints`, `chains`, `clasp`, `estimated_weight_18k_gold_g`.

`loop_hints.loop_positions_mm` — list of mm positions along the extender.

**Example:**
```json
{"file_id": "<uuid>", "extender_length_mm": 60.0, "loop_count": 6,
 "end_ring_style": "lobster"}
```

---

## How composed pieces reuse chain_assembly

Each composed piece calls `compute_chain_params()` internally and embeds the
resulting full `chain_assembly` sub-spec(s) in the `chains` list.  The
`opChainAssembly` worker evaluates each sub-spec exactly as it would a
top-level `chain_assembly` node.  Piece-specific hints (`stone_station_hints`,
`attach_hints`, `connector_hints`, `loop_hints`, `slide_hints`,
`terminal_hints`) are additive overlays — they do not replace or modify the
`chain_assembly` node-spec contract.

The `jewelry_create_chain` tool and worker contract are unchanged; all
existing styles and parameters continue to work without modification.
