# `sheet_metal_flange` — folded sheet-metal base plate + flange (T-1)

Appends a `sheet_metal_flange` node to a `.feature` file.  Produces a single
folded solid B-rep: a rectangular base plate with one bent flange along a
chosen top edge.  Wall thickness is uniform throughout.

> **Deferred (T-2 / T-3 / T-4)**: unfold / flat-pattern / bend table are
> separate follow-up tools.  This tool produces the *folded* geometry only.
> The `k_factor` stored on the node is consumed by `sheet_metal_unfold` (T-2,
> not yet shipped) to compute the neutral-axis developed length.

## Tool name

`sheet_metal_flange`

## Schema

```json
{
  "id": "sheet_metal_flange-1",
  "op": "sheet_metal_flange",
  "base_width": 100,
  "base_depth": 80,
  "thickness": 1.5,
  "edge_ref": "top-front",
  "flange_length": 25,
  "bend_angle_deg": 90,
  "bend_radius": 2,
  "k_factor": 0.44
}
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_id` | UUID string | — | Target `.feature` file (required). |
| `base_width` | number (mm) | 50 | X-dimension of the blank base plate. |
| `base_depth` | number (mm) | 50 | Y-dimension of the blank base plate. |
| `thickness` | number (mm) | 1.0 | Uniform sheet wall thickness. Must be > 0. |
| `edge_ref` | string | `"top-front"` | Which top edge to fold along. See edge reference below. |
| `flange_length` | number (mm) | 20 | Straight-wall length after the bend arc. Must be > 0. |
| `bend_angle_deg` | number (°) | 90 | How far the flange rotates from the base plane. Range (0, 180]. 90° = right-angle. |
| `bend_radius` | number (mm) | 1.0 | Inside radius of the bend arc. Must be > 0. |
| `k_factor` | number | 0.44 | Neutral-axis offset fraction, in (0, 1). Stored for unfold (T-2). |
| `id` | string | auto | Optional explicit node id. |

### `edge_ref` values

| Value | Description |
|---|---|
| `"top-front"` | Front edge of the top face (Y=0 side). Default. |
| `"top-back"` | Back edge (Y=base_depth side). |
| `"top-left"` | Left edge (X=−base_width/2 side). |
| `"top-right"` | Right edge (X=+base_width/2 side). |

Numeric edge references (`"edge-0"`, `"edge-3"`, etc.) from the inspector
are also accepted by the worker; the four named values are recommended for
LLM invocation.

### `k_factor` guidance

| Material | Typical k-factor |
|---|---|
| Hard / tool steel | 0.33 |
| Mild steel | 0.44 (default) |
| Stainless steel | 0.38 |
| Aluminium (5052) | 0.44–0.50 |
| Soft aluminium | 0.50 |

The k-factor does **not** change the folded geometry.  It is stored on the
node so that the unfold solver (T-2) can compute:
```
bend_allowance = (bend_radius + k_factor × thickness) × bend_angle_rad
```

## Geometry

1. **Base plate** — a box `base_width × base_depth × thickness` at Z = 0,
   centred on X.
2. **Bend arc** — a cylindrical sector of inner radius `bend_radius` and outer
   radius `bend_radius + thickness`, swept through `bend_angle_deg` about the
   chosen fold edge.
3. **Flange wall** — a rectangular prism of length `flange_length`, thickness
   `thickness`, width `base_width`, in the direction tangent to the arc at the
   far end.
4. The three volumes are **fused** into one watertight solid.

### OCCT-binding note

The bend arc is built with `BRepPrimAPI_MakeCylinder` (sector form) rather
than `BRepOffsetAPI_MakeOffsetShape` (not exposed in the current WASM build).
This is geometrically equivalent for the folded-shape purpose and does not
require additional WASM capabilities.

## Validation errors

| Code | Condition |
|---|---|
| `BAD_ARGS` | `edge_ref` is empty. |
| `BAD_ARGS` | `flange_length <= 0`. |
| `BAD_ARGS` | `bend_angle_deg` not in (0, 180]. |
| `BAD_ARGS` | `bend_radius <= 0`. |
| `BAD_ARGS` | `thickness <= 0`. |
| `BAD_ARGS` | `k_factor` not strictly in (0, 1). |
| `BAD_ARGS` | `base_width <= 0` or `base_depth <= 0`. |
| `NOT_FOUND` | `file_id` not found or is not a `.feature` file. |

## Example: 90° right-angle bracket

```python
result = await client.call("sheet_metal_flange", {
    "file_id": "<feature-file-uuid>",
    "base_width": 120,
    "base_depth": 80,
    "thickness": 2.0,
    "edge_ref": "top-front",
    "flange_length": 40,
    "bend_angle_deg": 90,
    "bend_radius": 3,
    "k_factor": 0.44,
})
```

Produces a 120 × 80 × 2 mm flat base with a 40 mm upright flange at the
front edge, inside bend radius 3 mm, suitable for a mild-steel bracket.

## Example: obtuse return flange

```python
result = await client.call("sheet_metal_flange", {
    "file_id": "<feature-file-uuid>",
    "base_width": 60,
    "base_depth": 40,
    "thickness": 1.2,
    "edge_ref": "top-back",
    "flange_length": 15,
    "bend_angle_deg": 135,
    "bend_radius": 1.5,
    "k_factor": 0.38,   # stainless
})
```

## Response

```json
{
  "ok": true,
  "data": {
    "file_id": "<uuid>",
    "id": "sheet_metal_flange-1",
    "op": "sheet_metal_flange",
    "edge_ref": "top-front",
    "flange_length": 25.0,
    "bend_angle_deg": 90.0,
    "bend_radius": 2.0,
    "thickness": 1.5,
    "k_factor": 0.44,
    "note": "Folded B-rep produced. Unfold / flat-pattern: use sheet_metal_unfold (T-2, not yet shipped)."
  }
}
```

## Roadmap / follow-ups

| Task | Description |
|---|---|
| T-2 | `sheet_metal_unfold` — neutral-axis bend-allowance unfold solver |
| T-3 | `sheet_metal_flat_pattern` — 2D outline + bend lines, DXF export |
| T-4 | `sheet_metal_bend_table` — material-specific allowance lookup from DB |
