# Phase 4a — jewelry-priority surfacing

Three Rhino-flavored NURBS ops live inside `.feature` files alongside the
core pad / pocket / fillet vocabulary: **sweep2**, **network_srf**,
**blend_srf**. Each is also wired as a typed LLM tool so you can compose
ring shanks, prong baskets, and bezels from a sentence of intent — no
write_file/edit_file needed.

When choosing between them:

| You want…                                                | Reach for       |
|----------------------------------------------------------|-----------------|
| A tube whose cross-section follows TWO curves             | `sweep2`        |
| A patch fitted to a 4-or-more-curve U/V edge grid          | `network_srf`   |
| A smooth bridge between two existing edges                 | `blend_srf`     |
| A simple sweep along ONE rail                              | `sweep1` (Phase 4 starter) |
| Cross-section morph between ≥2 closed profiles             | `loft` (Phase 4 starter)   |

All three append nodes to the host `.feature` file's `features` array.
You can author them via `feature_sweep2` / `feature_network_srf` /
`feature_blend_srf`, or hand-edit JSON after consulting `feature.md`.

## `sweep2` — twin-rail sweep

```json
{
  "id": "sweep2-1",
  "op": "sweep2",
  "profile_sketch_path": "/profiles/oval.sketch",
  "rail1_sketch_path":   "/rails/inside.sketch",
  "rail2_sketch_path":   "/rails/outside.sketch",
  "twist_deg": 0,
  "scale_end": 1,
  "mode": "auto"
}
```

Wraps `BRepOffsetAPI_MakePipeShell` with rail1 as the spine and rail2
registered as the auxiliary spine (`SetMode_3`). The profile is the
closed outer wire of the profile face.

**Example — ring shank.** A 4mm × 2mm oval profile (one closed sketch on
XY) sweeps along an inside-of-the-band curve and an outside-of-the-band
curve (both on XZ). The profile rotates and scales as needed to keep its
top edge tangent to rail2.

```text
feature_sweep2(
  file_id  = <ring.feature id>,
  profile_path = "/profiles/oval-4x2.sketch",
  rail1_path   = "/rails/shank-inside.sketch",
  rail2_path   = "/rails/shank-outside.sketch"
)
```

If the OCCT build's auxiliary-spine binding isn't available the worker
falls back to a Frenet sweep along rail1 alone and surfaces a console
warning — rail2 is honoured when possible, advisory otherwise.

## `network_srf` — surface from a U/V grid

```json
{
  "id": "network_srf-1",
  "op": "network_srf",
  "u_curves": [
    "/u/edge-front.sketch",
    "/u/edge-back.sketch"
  ],
  "v_curves": [
    "/v/edge-left.sketch",
    "/v/edge-right.sketch"
  ],
  "continuity": "C1"
}
```

Fits a NURBS surface across a grid of 2-or-more curves in each direction.
For organic prong baskets, wave-pattern bezels, or any double-curvature
patch you'd reach for in Rhino's `NetworkSrf`.

When the OCCT build exposes `GeomFill_BSplineCurves` plus the BSpline
conversion helpers, the worker uses that 4-curve patch primitive (exact
U0/U1/V0/V1 boundary). Otherwise it falls back to
`BRepOffsetAPI_ThruSections` over the U-curves alone (V-curves remain
advisory) — you'll get a useful surface but it may not exactly meet the
V boundary edges.

**Example — prong basket cap.** Four sketched curves form the basket's
front/back/left/right rim:

```text
feature_network_srf(
  file_id = <basket.feature id>,
  u_paths = ["/rim/front.sketch", "/rim/back.sketch"],
  v_paths = ["/rim/left.sketch",  "/rim/right.sketch"],
  options = { continuity: "C2" }
)
```

## `blend_srf` — smooth bridge between two edges

```json
{
  "id": "blend_srf-1",
  "op": "blend_srf",
  "target_id": "pad-1",
  "edge1_id": 7,
  "edge2_id": 23,
  "continuity": "G1"
}
```

Builds a `BRepFill_Filling` face constrained by two existing edges of
the upstream body. Use this when you want a smooth bezel cap that ties
the top edge of a pad-extruded ring band to the bottom edge of a setting
collar.

`continuity`:
- `G0` — touches both edges, no tangent constraint.
- `G1` — tangent-continuous (visually smooth, default).
- `G2` — curvature-continuous (best for high-polish jewelry).

**Edge ids** are post-evaluation indices from the OCCT worker's TopExp
order. They're stable across pure parameter tweaks but renumber on
structural edits — the FeatureView's `Edges` pick mode shows them on
hover. The same caveat as `fillet` with `edge_filter: manual`.

**Example — bezel between two ring bands.**

```text
1. read_file("/rings/double-band.feature") to see the existing pads.
2. Open the feature in the editor, hover the two adjacent edges that
   need bridging, note their numeric ids.
3. feature_blend_srf(
     file_id  = <double-band.feature id>,
     target_id = "pad-2",
     edge1_id  = 12,
     edge2_id  = 34,
     options   = { continuity: "G2" }
   )
```

## `surface_continuity` — query or enforce continuity

Query or update the continuity tag on an existing surfacing node without
re-running the full feature evaluation.

```
surface_continuity(
  file_id       = <my.feature id>,
  node_id       = "network_srf-1",
  set_continuity = "C2"            # optional — omit to query only
)
```

Returns the node's current (or updated) continuity value plus the set of
valid values for that op type.

Continuity values by op:

| Op            | Valid values   | Default |
|---------------|----------------|---------|
| `sweep1`      | C0 / C1 / C2   | C1      |
| `sweep2`      | C0 / C1 / C2   | C1      |
| `network_srf` | C0 / C1 / C2   | C1      |
| `blend_srf`   | G0 / G1 / G2   | G1      |

C0 = positional (meets boundary). C1 = tangent-continuous. C2 = curvature-continuous.
G0/G1/G2 = geometric continuity (used for blend surfaces at existing B-rep edges).

## `.surf` file kind

A `.surf` file stores a pure NURBS surface description — the Python-side
`NurbsSurface` object serialised as JSON. Useful for scripting, inspection,
and LLM-accessible manipulation outside the `.feature` evaluation pipeline.

```json
{
  "version": 1,
  "degree_u": 3,
  "degree_v": 3,
  "control_points": [[[x, y, z], ...], ...],
  "knots_u": [0, 0, 0, 0, 1, 1, 1, 1],
  "knots_v": [0, 0, 0, 0, 1, 1, 1, 1]
}
```

The `control_points` field is a `(nu × nv × 3)` nested array.

Note: `.surf` files are Python-side only. Display in the 3D viewer happens
by tessellating the surface into a triangular mesh. For surfaces authored via
`feature_sweep2` / `feature_network_srf` / `feature_blend_srf`, the
tessellation is handled by the OCCT worker (the ops map to
`BRepOffsetAPI_MakePipeShell`, `GeomFill_BSplineCurves`, `BRepFill_Filling`);
the Python NurbsSurface objects in `backend/geom/` are the LLM-accessible
manipulation layer.

## Scope and limitations (Phase 4)

Phase 4 = **surface creation tools + display**. This is not Rhino-tier NURBS.

What is supported:
- sweep1, sweep2, network_srf, blend_srf surface creation via LLM tools
- C0/C1/C2 and G0/G1/G2 continuity tags (advisory — enforced where OCCT exposes the binding)
- Python-side NURBS evaluation (de Boor, derivatives, point-on-surface)
- surface_continuity query/enforce tool

What is explicitly NOT in scope for Phase 4:
- NURBS trimming (requires full OCCT NURBS kernel — years of work)
- NURBS boolean operations (same dependency)
- Exact Rhino-style `NetworkSrf` with all four boundary-fit modes
- Full curvature continuity enforcement across arbitrary surface networks

## Limitations

- The opencascade.js binding sometimes lacks specific overload numbers.
  When that happens the worker degrades gracefully and prints a console
  warning rather than fabricating a wrong surface; the produced shape
  still solves the user's intent at a slightly lower fidelity.
- `target_id` on `blend_srf` is recorded for traceability, but at
  evaluation time the worker operates on the most-recent threaded
  shape — exactly like `fillet` / `chamfer`. Don't depend on
  blend_srf reaching back across structural feature edits.
- `sweep2`'s `twist_deg` / `scale_end` parameters are recognized but
  not yet wired through to a Law function in this build (matches
  `sweep1`). They round-trip in the JSON.
