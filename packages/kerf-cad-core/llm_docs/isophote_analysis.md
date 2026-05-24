# Isophote Analysis + MatchSrf G3 (GK-P47)

Surfacing additions: isophote / environment-map continuity analysis
(`feature_isophote_analysis`), G3 curvature-rate continuity on the existing
`match_surface_edge_tool`, and guide-curve lofts via `feature_loft`
`guide_curve_paths` (see `feature_loft.md`).

---

## When to use

Reach for these tools when the user asks about:

- Checking whether a NURBS surface is G1-smooth (no tangent jumps visible in reflection lines)
- Class-A surface quality, reflection-line analysis, isophote continuity
- Matching a source surface edge to a target at G3 (curvature-rate) continuity
- Automotive Class-A, fine jewellery surfacing, mirror-quality industrial surfaces

---

## Tools

### `feature_isophote_analysis`

**Read-only analysis** — does NOT append a geometry node. Samples the
illumination scalar μ = n̂·L̂ over a UV grid and detects isophote breaks
(band index jumps ≥ 2 across adjacent cells — the visual signature of a G1
tangent discontinuity).

Returns: `has_break` (bool), `num_breaks` (int), analysis metadata.
The OCCT worker evaluates the surface and returns the full `mu_grid`,
`band_grid`, `gradient_grid`, `isophote_break_mask`, `normal_grid` in the
evaluation result.

**Required:** `file_id`, `target_id`
**Optional:** `uv_grid` ([nu, nv], default [48,48]), `sphere_map_res` (2–64, default 16), `light_dir` ([x,y,z], default [0,0,1])
**Returns:** `{file_id, target_id, analysis:"isophote", uv_grid, sphere_map_res, ...}`

---

### `match_surface_edge_tool` — G3 continuity (GK-P10 update)

The existing `match_surface_edge_tool` now accepts `continuity:"G3"` (in
addition to G0/G1/G2). G3 is curvature-rate continuity (dκ/ds matching) —
the highest analytic continuity class, required for automotive Class-A and
fine jewellery.

**G3 requirements:** source degree ≥ 3 AND ≥ 4 CP rows in the matched direction.

Returns `max_curvature_rate_deviation` (the G3 dκ/ds residual) in addition to
the standard G0/G1/G2 deviations.

See the `match_surface_edge_tool` ToolSpec for full parameter documentation.

---

### `feature_loft` — guide curves (GK-P16, already wired)

The `feature_loft` tool accepts `guide_curve_paths` — a list of `.sketch`
paths acting as guide rails. Each guide must intersect all profile sketches.
The OCCT worker routes guide curves through `BRepOffsetAPI_ThruSections.AddWire()`.
Incompatible with `symmetric: true`.

See `feature_loft.md` for full documentation.

---

## Example

**User ask:** "Check if my swept surface has any G1 breaks, then match the
adjacent surface edge to G3."

```
1. feature_isophote_analysis
     file_id:"<uuid>"
     target_id:"sweep1-1"
     uv_grid:[48, 48]
     sphere_map_res:16
     light_dir:[0.5, 0, 1]
   → {target_id:"sweep1-1", analysis:"isophote", ...}

2. match_surface_edge_tool
     target_degree_u:3  target_degree_v:3
     target_control_points:[...] target_num_u:8  target_num_v:8
     target_edge:"u0"
     source_degree_u:3  source_degree_v:3
     source_control_points:[...] source_num_u:8  source_num_v:8
     source_edge:"u1"
     continuity:"G3"
   → {ok:true, max_curvature_rate_deviation:2.3e-7, continuity_achieved:"G3"}
```

---

## Notes

- `feature_isophote_analysis` is read-only; no geometry is appended.
- `match_surface_edge_tool` G3 requires degree ≥ 3 on both surfaces.
- Use `feature_isophote_analysis` before and after a match-srf step to confirm
  the break is resolved.
- For `feature_loft` guide curves, see `feature_loft.md`.
