# NURBS Surfacing Tools

Core surfacing toolkit for `.feature` files: sweep, network surface, blend surface,
surface booleans, trim by curve, continuity control, and curvature-comb visualisation.
All tools append a node to an existing `.feature` file; geometry is evaluated by the
OCCT worker. Continuity vocabulary: C0/C1/C2 = parametric; G0/G1/G2 = geometric.

---

## When to use

Reach for these tools when the user asks about:

- sweeping a profile along a path (`feature_sweep1`) or two rails (`feature_sweep2`)
- fitting a NURBS surface through a grid of U/V curves (`feature_network_srf`)
- building a fillet or transition surface between two edges (`feature_blend_srf`)
- promoting a surface body to a solid for downstream booleans (`feature_to_solid`)
- CSG operations (cut / fuse / common) between two solid bodies (`feature_boolean`)
- surface-direct booleans that skip the solid round-trip (`feature_surface_boolean`)
- trimming a NURBS face by projecting a 3D curve onto it (`feature_trim_by_curve`)
- checking or changing continuity (C0/C1/C2, G0/G1/G2) on a surfacing node (`surface_continuity`)
- displaying curvature combs for G2/G3 continuity inspection (`feature_surface_curvature_combs`)
- Class-A surfacing, ring shank blends, automotive bodyside fillets, boat hull fairings
- anything involving surface continuity, surface quality, or reflection-line readiness

---

## Tools

### `feature_sweep1`

Append a `sweep1` node. Sweeps a closed profile sketch along **one** open-curve path
using `BRepOffsetAPI_MakePipeShell`. Frame modes: `auto` (default), `frenet`,
`corrected_frenet` (eliminates roll on coils and high-curvature paths — prefer this
for jewellery shanks and helix paths).

**Required:** `file_id`, `profile_sketch_path`, `path_sketch_path`
**Optional:** `scale` (default 1.0), `twist_deg` (default 0), `mode` (`auto`/`frenet`/`corrected_frenet`), `id`
**Returns:** `{file_id, id, op:"sweep1"}`

---

### `feature_sweep2`

Append a `sweep2` node. Sweeps a closed profile along **two** open-curve rails
(two-rail sweep / `BRepOffsetAPI_MakePipeShell` with two guides). Controls section
scale at the end (`scale_end`) and optional twist.

**Required:** `file_id`, `profile_sketch_path`, `rail1_sketch_path`, `rail2_sketch_path`
**Optional:** `twist_deg`, `scale_end` (default 1), `mode`, `id`
**Returns:** `{file_id, id, op:"sweep2"}`

---

### `feature_network_srf`

Append a `network_srf` node. Fits a NURBS surface through a U/V grid of curves
(at least 2 U curves and 2 V curves). Continuity `C0`/`C1`/`C2` (default `C1`)
controls how smoothly the surface follows the guide curves.

**Required:** `file_id`, `u_paths` (list, ≥ 2), `v_paths` (list, ≥ 2)
**Optional:** `options.continuity` (`C0`/`C1`/`C2`), `options.id`
**Returns:** `{file_id, id, op:"network_srf"}`

---

### `feature_blend_srf`

Append a `blend_srf` node. Builds a G0/G1/G2 transition surface between two edges
of an existing feature body. Default continuity is `G1` (tangent-continuous).
`blend_dist` controls the pull-back distance on both sides of the seam.

**Required:** `file_id`, `target_id`, `edge1_id`, `edge2_id`
**Optional:** `options.continuity` (`G0`/`G1`/`G2`, default `G1`), `options.blend_dist`, `options.id`
**Returns:** `{file_id, id, op:"blend_srf"}`

---

### `feature_to_solid`

Append a `to_solid` node. Promotes a surface body (Face/Shell/sewn-face collection)
to a `TopoDS_Solid` via `BRepBuilderAPI_Sewing` + `MakeSolid`. Required before
`feature_boolean` can consume a surface-origin body. Raise `tolerance` (e.g. `1e-5`)
for noisy NURBS that fail to sew at the default `1e-6`.

**Required:** `file_id`, `target_id`
**Optional:** `options.tolerance` (default `1e-6`), `options.id`
**Returns:** `{file_id, id, op:"to_solid"}`

---

### `feature_boolean`

Append a `boolean` node. CSG between two **solid** feature bodies:
`cut` = A − B, `fuse` = A ∪ B, `common` = A ∩ B. Both operands must resolve to
`TopoDS_Solid` — run `feature_to_solid` first if either is a surface body.

**Required:** `file_id`, `target_a_id`, `target_b_id`, `kind` (`cut`/`fuse`/`common`)
**Optional:** `options.id`
**Returns:** `{file_id, id, op:"boolean", kind}`

---

### `feature_surface_boolean`

Append a `surface_boolean` node. Surface-direct CSG that accepts Face, Shell, or
Solid operands — no `feature_to_solid` step needed. Returns a compound of trimmed
face fragments. Uses `ShapeFix_Shape` pre-passes and `ShapeUpgrade_UnifySameDomain`
cleanup. Tune `fuzziness` (default `1e-4`) if face fragments go missing at tangent
intersections. Set `coarse_mode: true` to skip cleanup passes for fast previews.

**Required:** `file_id`, `target_a_id`, `target_b_id`, `kind`
**Optional:** `fuzziness` (positive number), `coarse_mode` (bool), `options.id`
**Returns:** `{file_id, id, op:"surface_boolean", kind}`

---

### `feature_trim_by_curve`

Append a `trim_by_curve` node. Projects a 3D curve onto a NURBS face and splits
the face along that projection, keeping one side. Useful for cutting windows into
ring shoulders or removing regions from blend surfaces without a solid round-trip.

**Required:** `file_id`, `target_feature_ref`, `target_face_name` (positional, e.g. `face-1`), `trim_curve_ref`
**Optional:** `keep_side` (`positive`/`negative`, default `positive`), `tolerance` (default `1e-3`), `options.id`
**Warning:** trim invalidates positional face-N IDs until persistent-face-naming ships.
**Returns:** `{file_id, id, op:"trim_by_curve", keep_side}`

---

### `surface_continuity`

Query or enforce continuity on a surfacing node. If `set_continuity` is omitted,
returns the current value and the list of valid values. Use C0/C1/C2 for
`sweep1`/`sweep2`/`network_srf`; use G0/G1/G2 for `blend_srf`.

**Required:** `file_id`, `node_id`
**Optional:** `set_continuity` (`C0`/`C1`/`C2`/`G0`/`G1`/`G2`)
**Returns (query):** `{continuity, valid_values, op}`
**Returns (set):** `{continuity_before, continuity_after, op}`

---

### `feature_surface_curvature_combs`

Append a `surface_curvature_combs` node. Samples principal curvatures (k1/k2, mean,
Gaussian) on a NURBS body via `GeomLProp_SLProps` and renders an interactive
curvature-comb overlay in the viewport (Three.js `LineSegments`: blue=concave,
red=convex, white=flat; line length = curvature × `scale_factor`). Use to verify
G2/G3 continuity at face junctions visually — the standard Class-A workflow.

**Note:** Visualisation only. Algorithmic G3 enforcement is not possible in stock
OCCT (`GeomAbs_G3` absent from `GeomAbs_Shape` enum).

**Required:** `file_id`, `target_feature_ref`
**Optional:** `target_face_name` (sample one face only), `uv_density` (0.01–0.5, default 0.1), `scale_factor` (default 10), `show_combs` (bool), `options.id`
**Returns:** `{file_id, node_id, op:"surface_curvature_combs", target_feature_ref}`

---

## Example

**User ask:** "Sweep a circular cross-section along a spline path on a ring shank,
then blend the ends with G2 continuity and inspect with curvature combs."

```
1. feature_sweep1
     file_id:"<uuid>"
     profile_sketch_path:"/proj/circle.sketch"
     path_sketch_path:"/proj/shank_path.sketch"
     mode:"corrected_frenet"
   → {id:"sweep1-1", op:"sweep1"}

2. feature_blend_srf
     file_id:"<uuid>"
     target_id:"sweep1-1"
     edge1_id:3  edge2_id:7
     options:{continuity:"G2", blend_dist:1.5}
   → {id:"blend_srf-1", op:"blend_srf"}

3. surface_continuity
     file_id:"<uuid>"  node_id:"blend_srf-1"
   → {continuity:"G2", valid_values:["G0","G1","G2"]}

4. feature_surface_curvature_combs
     file_id:"<uuid>"
     target_feature_ref:"blend_srf-1"
     uv_density:0.05  scale_factor:15
   → {op:"surface_curvature_combs", node_id:"surface_curvature_combs-1"}
```

---

## Notes

- All tools write to a `.feature` file; the OCCT worker evaluates on next render.
- `feature_surface_boolean` is preferred over `feature_boolean` + `feature_to_solid`
  for pure-surface workflows (faster, avoids sewing artifacts).
- Zebra / reflection-line overlay is toggled in the viewport (top-right "Zebra" button);
  it uses a `ShaderMaterial` — no WASM rebuild needed.
- Algorithmic G3 is deferred; `feature_surface_curvature_combs` is the approved
  visualisation substitute for G3 continuity checks.
