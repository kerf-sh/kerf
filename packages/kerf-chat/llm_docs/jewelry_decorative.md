# jewelry_decorative — Applied Decorative Features

## Overview

Six write tools for applied decorative surface operations.  Each tool appends
a `decorative_apply` node to a `.feature` file.  The node carries a
`target_ref` (id of an existing edge, face, or curve in the same file) plus
`decorative_hints` consumed by the occtWorker `opDecorativeApply` handler.

| Tool | Target | Purpose |
|------|--------|---------|
| `jewelry_apply_milgrain` | edge / curve | Beaded-edge milgrain row |
| `jewelry_apply_beading` | face | Raised bright-cut grain field |
| `jewelry_apply_filigree` | face / closed curve | Scroll/lace motif tile fill |
| `jewelry_apply_twisted_wire` | curve (path) | Multi-strand wire/rope/braid trim |
| `jewelry_apply_scrollwork` | edge | Engraved-relief border motif |
| `jewelry_apply_surface_texture` | face | Surface-finish hint |

> **FeatureView note**: `opDecorativeApply` is stubbed; visual preview is
> deferred to a future milestone.  Nodes are stored and round-trip cleanly.

---

## Node-spec schema

All six tools produce nodes with this common envelope:

```json
{
  "id":               "<auto-assigned or explicit>",
  "op":               "decorative_apply",
  "feature":          "<milgrain|beading|filigree|twisted_wire|scrollwork|surface_texture>",
  "target_ref":       "<edge-id | face-id | curve-id>",
  "decorative_hints": { ... }
}
```

`target_ref` is **always required** — it is the id of an existing geometry
entity in the same `.feature` file.

---

## jewelry_apply_milgrain

Apply a row of small hemispherical beads along an edge — the classic vintage
milgrain treatment.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the target edge or curve |
| `bead_diameter_mm` | number | Bead diameter in mm (typical 0.3–1.5) |
| `pitch_mm` | number | Centre-to-centre spacing in mm |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `profile` | `"round"` | Bead shape: `round`, `flat_top`, `pointed` |
| `offset_mm` | `0.0` | Lateral offset from edge centreline (signed) |

### `decorative_hints` fields

```json
{
  "bead_diameter_mm": float,
  "pitch_mm":         float,
  "profile":          "round" | "flat_top" | "pointed",
  "offset_mm":        float
}
```

---

## jewelry_apply_beading

Apply raised bright-cut grain-work across a face.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the target face |
| `grain_diameter_mm` | number | Grain diameter in mm (typical 0.4–1.2) |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `seat_depth_fraction` | `0.5` | Seat depth as fraction of grain diameter (0–1] |
| `pattern` | `"hex"` | Layout: `grid`, `hex`, `random` |
| `row_count` | `4` | Rows (grid/hex) |
| `col_count` | `4` | Columns (grid/hex) |
| `grain_shape` | `"hemisphere"` | `sphere`, `hemisphere`, `cone` |
| `density` | `1.0` | Grains per mm² (random pattern) |
| `random_seed` | `42` | Reproducibility seed (random pattern) |

### `decorative_hints` fields

```json
{
  "grain_diameter_mm":   float,
  "seat_depth_mm":       float,
  "seat_depth_fraction": float,
  "pattern":             "grid" | "hex" | "random",
  "grain_shape":         "sphere" | "hemisphere" | "cone",
  // grid/hex only:
  "row_count":           int,
  "col_count":           int,
  "layout":              "offset_rows",   // hex only
  // random only:
  "density_per_mm2":     float,
  "random_seed":         int
}
```

---

## jewelry_apply_filigree

Tile a scroll/lace/arabesque/fleur openwork motif across a fill region.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the fill region (face or closed planar curve) |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `motif` | `"scroll"` | `scroll`, `lace`, `arabesque`, `fleur` |
| `scale` | `1.0` | Tile scale factor (> 0) |
| `density` | `1.0` | Packing density (> 0; 1.0 = normal) |
| `wire_gauge_mm` | `0.5` | Wire cross-section diameter in mm |
| `fill` | `true` | `true` = tile full region; `false` = single centred motif |

### `decorative_hints` fields

```json
{
  "motif":          "scroll" | "lace" | "arabesque" | "fleur",
  "scale":          float,
  "density":        float,
  "wire_gauge_mm":  float,
  "fill":           boolean
}
```

---

## jewelry_apply_twisted_wire

Sweep a multi-strand wire/rope/braid trim along a path curve.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the path curve |
| `strand_count` | integer (≥ 2) | Number of wire strands |
| `wire_gauge_mm` | number | Per-strand wire diameter in mm |
| `twist_pitch_mm` | number | Axial advance per full 360° twist in mm |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `braid_pattern` | `"twisted"` | `twisted`, `rope`, `braid` |

### `decorative_hints` fields

```json
{
  "strand_count":      int,
  "wire_gauge_mm":     float,
  "twist_pitch_mm":    float,
  "braid_pattern":     "twisted" | "rope" | "braid",
  "bundle_diameter_mm": float   // derived: gauge × (1 + strand_count × 0.8)
}
```

---

## jewelry_apply_scrollwork

Apply a repeating engraved-relief border motif along an edge.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the target edge |
| `style` | string | `scallop`, `scroll`, `leaf`, `acanthus` |
| `relief_depth_mm` | number | Engraved depth in mm (0–5) |
| `pitch_mm` | number | Motif spacing in mm |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mirror` | `true` | Mirror-alternate motifs for symmetric border |

### `decorative_hints` fields

```json
{
  "style":            "scallop" | "scroll" | "leaf" | "acanthus",
  "relief_depth_mm":  float,
  "pitch_mm":         float,
  "mirror":           boolean
}
```

---

## jewelry_apply_surface_texture

Apply a surface-finish hint to a named face.

### Required parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (uuid) | Target `.feature` file |
| `target_ref` | string | Id of the target face |
| `texture_type` | string | `hammered`, `florentine`, `satin`, `sandblast` |

### Optional parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `intensity` | `0.7` | Texture intensity (0–1] |
| `direction_deg` | `0.0` | Grain direction for florentine/satin (degrees) |

### `decorative_hints` fields

```json
{
  "texture_type": "hammered" | "florentine" | "satin" | "sandblast",
  "intensity":    float,
  // directional (florentine, satin):
  "direction_deg": float,
  // hammered:
  "facet_distribution": "random",
  "facet_size_relative": float,
  // florentine:
  "line_family_count": 2,
  "line_spacing_mm": float,
  // satin:
  "scratch_direction": "parallel",
  "scratch_depth_relative": float,
  // sandblast:
  "grain_size": "fine" | "medium",
  "matte": true
}
```

---

## Validation rules summary

| Op | Key constraints |
|----|----------------|
| milgrain | `bead_diameter_mm > 0`; `pitch_mm > 0`; `target_ref` non-empty |
| beading | `grain_diameter_mm > 0`; `seat_depth_fraction` in (0, 1] |
| filigree | `wire_gauge_mm ≤ 5 mm`; `scale > 0`; `density > 0` |
| twisted_wire | `strand_count ≥ 2`; `wire_gauge_mm ≤ 10 mm`; `twist_pitch_mm > 0` |
| scrollwork | `relief_depth_mm` in (0, 5] |
| surface_texture | `intensity` in (0, 1] |

All ops: `target_ref` is required and must be a non-empty string.
