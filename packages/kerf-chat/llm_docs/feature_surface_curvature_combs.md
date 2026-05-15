# `feature_surface_curvature_combs` — curvature-comb overlay on NURBS surfaces

Appends a `surface_curvature_combs` node to a `.feature` file. The worker
samples principal curvatures (k₁, k₂, mean, Gaussian) on the target feature's
NURBS faces via `GeomLProp_SLProps` and drives a Three.js overlay in the
viewport: orthogonal line segments at each UV sample point, scaled by curvature
magnitude, coloured by sign (blue = concave k < 0, red = convex k > 0, white =
flat k ≈ 0).

Use this to **eyeball G2/G3 continuity at face junctions** — the standard
workflow in automotive Class-A surfacing and jewelry CAD. After building a
`blend_srf` between a shank sweep and a bezel, inspect the curvature combs at
the seam to confirm the tangency blend looks smooth.

## Algorithmic G3 gap — honest status

**GeomAbs_G3 does not exist in the `GeomAbs_Shape` enum in stock OCCT.**
This makes algorithmic G3 continuity enforcement structurally impossible without
custom work:

| Enforcement path | Status |
|---|---|
| Stock `BRepFill_Filling` / `BRepOffsetAPI_*` | No G3 constraint argument |
| `GeomAbs_Shape` enum | Values: C0, G1, C1, G2, C2, C3, CN — **no G3** |
| Viz-only (curvature combs) | **Shipped** — this tool |
| Custom WASM rebuild | Would need a G3-aware constraint solver in C++ (e.g. iterative pole-adjustment minimising third-derivative mismatch at seam) — large undertaking outside the opencascade.js project scope |
| Approximation in Python | Could iterate `Geom_BSplineSurface.SetPole()` to minimise higher-order derivatives numerically — experimental, no production reference |

The curvature-combs overlay is the recommended path: build surfaces to G2
(which OCCT enforces), then refine by visually inspecting combs.

## Colormap

| Colour | Meaning | Curvature range |
|--------|---------|----------------|
| Blue | Concave (k < 0) | mean curvature < −threshold |
| White | Flat / saddle | mean curvature ≈ 0 |
| Red | Convex (k > 0) | mean curvature > +threshold |

The threshold is auto-scaled to `max(|mean curvature|) × 0.1` so the colormap
always uses the full blue-white-red range regardless of absolute curvature values.

## Schema

```json
{
  "id": "surface_curvature_combs-1",
  "op": "surface_curvature_combs",
  "target_feature_ref": "blend_srf-1",
  "uv_density": 0.1,
  "scale_factor": 10,
  "show_combs": true
}
```

### Parameters

| Parameter            | Type          | Required | Default | Notes                                                                      |
|----------------------|---------------|----------|---------|----------------------------------------------------------------------------|
| `file_id`            | string (uuid) | yes      | —       | Target `.feature` file id                                                   |
| `target_feature_ref` | string        | yes      | —       | Node id of the feature to sample (e.g. `"blend_srf-1"`, `"sweep1-2"`)     |
| `target_face_name`   | string        | no       | all     | Sample only the named face (`"face-0"`, `"face-1"`, …); default = all faces |
| `uv_density`         | number        | no       | `0.1`   | UV grid step as fraction of param range. 0.1 → ~10×10 per face. Range: (0, 0.5] |
| `scale_factor`       | number        | no       | `10`    | Comb length multiplier: `length = maxAbs × scale_factor`. Increase for flat surfaces |
| `show_combs`         | boolean       | no       | `true`  | Initial overlay visibility. User can toggle in the overlay panel            |
| `options.id`         | string        | no       | auto    | Explicit node id (`"surface_curvature_combs-N"`)                            |

## Worked examples

### Inspect a blend surface at the shank–bezel junction

```json
{
  "id": "surface_curvature_combs-1",
  "op": "surface_curvature_combs",
  "target_feature_ref": "blend_srf-1",
  "uv_density": 0.05,
  "scale_factor": 15,
  "show_combs": true
}
```

Fine grid (0.05 = ~20×20), longer combs for a small high-curvature bezel blend.

### Spot-check one face only

```json
{
  "id": "surface_curvature_combs-2",
  "op": "surface_curvature_combs",
  "target_feature_ref": "network_srf-1",
  "target_face_name": "face-0",
  "uv_density": 0.1,
  "scale_factor": 10
}
```

### Automotive hood surface — coarse preview

```json
{
  "id": "surface_curvature_combs-1",
  "op": "surface_curvature_combs",
  "target_feature_ref": "sweep1-1",
  "uv_density": 0.25,
  "scale_factor": 50
}
```

Large `scale_factor` because an automotive panel has very low curvature (nearly
flat) — without amplification the combs would be invisible.

## Binding probe status

From the NURBS Phase 4 boot probe (`_logNurbsPhase4Bindings`):

| Class | Probe constant | Status (static analysis) |
|-------|---------------|--------------------------|
| `GeomLProp_SLProps` | `NURBS_PHASE4_C4_BINDINGS[1]` | Likely OK — already used in walkSideFaces, surface_continuity, 5-axis CAM drive-face extraction |
| `BRepLProp_SLProps` | `NURBS_PHASE4_C4_BINDINGS[0]` | Unknown — probed at boot; not used by this tool (we use Geom variant) |

The `GeomLProp_SLProps_2(surf, u, v, order, tol)` constructor form is confirmed
present in the current build (multiple call sites in `occtWorker.js`).
`IsCurvatureDefined()`, `MaxCurvature()`, `MinCurvature()`, and
`MaxCurvatureDirection()` are new call sites for this codebase but are standard
OCCT methods on the same class.

If the boot log shows `GeomLProp_SLProps: MISSING`, `opSurfaceCurvatureCombs`
posts an empty `surface_curvature_combs_result` with `geomLPropSLPropsPresent: false`
and the overlay panel shows "Curvature probe unavailable on this OCCT build."

## Error codes

| Code | Cause |
|------|-------|
| `BAD_ARGS` | `file_id` not a uuid; `target_feature_ref` missing; `uv_density` ≤ 0 or > 0.5; `scale_factor` ≤ 0 |
| `NOT_FOUND` | File not found or not a `.feature` file |
| `ERROR` | JSON encode failure or DB write failure |

Worker-side errors (e.g. target_feature_ref not in evaluated tree) are surfaced
as a standard worker error envelope — the overlay shows the error text in the
overlay panel.
