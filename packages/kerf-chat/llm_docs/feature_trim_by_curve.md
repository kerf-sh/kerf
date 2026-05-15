# feature_trim_by_curve

**Tool name:** `feature_trim_by_curve`
**Op kind:** `trim_by_curve`
**Phase:** NURBS Phase 4 Capability 2 (C2-T3)
**Category:** Surfacing

## What it does

Splits a NURBS face along the UV-space projection of a 3D curve, keeping one
side as the new current shape.  The complementary side is discarded (but
visible in the intermediate inspector result — swap `keep_side` to see it).

Typical use cases:
- Cut a stone-setting window into a ring shoulder.
- Remove a teardrop region from a blend surface before sewing.
- Notch a sweep face at a sketch curve.
- Split an architectural NURBS panel along a non-planar crease.

## Schema

```json
{
  "file_id":            "<uuid>",
  "target_feature_ref": "<feature_node_id>",
  "target_face_name":   "face-1",
  "trim_curve_ref":     "/project/curves/cut.sketch",
  "keep_side":          "positive",
  "tolerance":          1e-3
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string (UUID) | yes | Target `.feature` file. |
| `target_feature_ref` | string | yes | Node id of the feature whose face to trim.  Must be an earlier node in the same file. |
| `target_face_name` | string | yes | Positional face id (`face-1`, `face-3`, …) from the inspector face list. |
| `trim_curve_ref` | string | yes | Absolute `.sketch` path **or** id of an already-evaluated feature body whose shape acts as the 3D cutter wire. |
| `keep_side` | `"positive"` \| `"negative"` | no | Which side of the split to keep (default `"positive"` = `BRepFeat_SplitShape.Left()`).  Swap to `"negative"` if the wrong side is kept. |
| `tolerance` | number | no | Projection + split tolerance in model units (default `1e-3`).  Raise to `1e-2` if the projected wire has C1 discontinuities. |
| `options.id` | string | no | Explicit node id (auto-generated as `trim_by_curve-N` if absent). |

## Worker algorithm

1. Resolve `target_feature_ref` in `bodyMap` (or use `prev` if absent).
2. Extract the face identified by `target_face_name` via `TopExp_Explorer` (positional index).
3. Resolve `trim_curve_ref` as a sketch wire (`wireForSketchPath`) or a body from `bodyMap`.
4. `projectCurveOntoSurface(oc, face, wire3d, tracker)`:
   - **Primary**: `BRepProj_Projection(wire, face, direction)` → projected wire with 2D pcurves.
   - **Fallback**: sample the 3D wire at 32 points → `GeomAPI_ProjectPointOnSurf` per point → stitch via `BRepBuilderAPI_MakeEdge` + `MakeWire`.
5. `splitFaceAlongCurve(oc, face, projectedWire, tracker)`:
   - **Primary**: `BRepFeat_SplitShape(face)` + `.Add(wire, face)` + `.Build()` → `.Left()` / `.Right()`.
   - **Fallback**: `TrimByCurveUnsupportedError` with C2-T12 escalation hint.
6. Return kept side per `keep_side`.

## Example — cut a window into a ring shoulder

```python
# Step 1: build the ring shoulder surface
feature_sweep1(
    file_id="<fid>",
    profile_sketch_path="/ring/profile.sketch",
    path_sketch_path="/ring/path.sketch"
)

# Step 2: create the window outline as a sketch on the shoulder
# (use the sketch tool to draw an oval on the shoulder face)

# Step 3: trim the shoulder face along the window outline
feature_trim_by_curve(
    file_id="<fid>",
    target_feature_ref="sweep1-1",
    target_face_name="face-1",
    trim_curve_ref="/ring/window_outline.sketch",
    keep_side="positive"   # keep the shoulder; discard the oval cutout region
)
```

Resulting feature tree JSON node:

```json
{
  "id": "trim_by_curve-1",
  "op": "trim_by_curve",
  "target_feature_ref": "sweep1-1",
  "target_face_name": "face-1",
  "trim_curve_ref": "/ring/window_outline.sketch",
  "keep_side": "positive"
}
```

## Binding-probe gate (C2)

The worker probes these classes at boot (`[occt-phase4] C2 (trim-by-curve) — <class>: OK|MISSING`):

| Class | Role | Risk |
|---|---|---|
| `BRepFeat_SplitShape` | Primary face splitter | **High** — niche `BRepFeat` class; may be absent |
| `BRepProj_Projection` | Primary projection | Medium |
| `GeomAPI_ProjectPointOnSurf` | Per-point fallback projection | Low |
| `ShapeAnalysis_Surface` | Surface param helper | Low |
| `BRepBuilderAPI_MakeEdge` | Edge builder for fallback | Low (standard) |
| `BRepBuilderAPI_MakeWire` | Wire builder for fallback | Low (standard) |
| `BRepBuilderAPI_MakeFace` | Face builder | Low |
| `BRepBuilderAPI_MakeFace_18` | Face+wire overload | Medium |
| `ShapeFix_Wire` | Wire cleanup | Low |

If `BRepFeat_SplitShape` is **MISSING**, the op throws `TrimByCurveUnsupportedError` and the
worker surfaces a clear escalation message: *"Escalate to C2-T12 (Section+prism fallback or
WASM rebuild)."*

## Persistent-face-naming caveat

**This op invalidates positional `face-N` IDs.**  When `trim_by_curve` splits `face-1` into
two faces, all downstream ops that reference either fragment by `face-N` id will break on
re-evaluation.  This is a known limitation of the positional naming scheme — it will be fixed
when [persistent face naming](../../docs/plans/persistent-face-naming.md) ships.

Workaround: place `trim_by_curve` as the **last surfacing op** in the tree, or avoid
referencing the trimmed face downstream until persistent naming lands.

## Error codes

| Message pattern | Cause | Fix |
|---|---|---|
| `target_face_name is required` | `target_face_name` absent | Add the `face-N` id |
| `target body '…' not found` | `target_feature_ref` not in bodyMap | Ensure the referenced node precedes this one |
| `face 'face-N' not found` | Index out of range | Check inspector face count |
| `trim_curve_ref '…' not found` | Sketch path or feature id invalid | Fix the path or ensure the feature is evaluated earlier |
| `failed to project` | Curve misses the face | Reposition the sketch so it crosses the face |
| `TrimByCurveUnsupportedError` | `BRepFeat_SplitShape` absent | Escalate to C2-T12 |
| `split produced no 'positive' side` | Cutter doesn't cross face boundary | Extend the sketch or try `keep_side: "negative"` |

## Related tools

- `feature_surface_boolean` — surface-direct boolean (union/difference/intersection) for two
  face/shell bodies.  Use when you want to subtract one surface from another rather than trim
  a single face by a curve.
- `feature_to_solid` — promote a NURBS surface to a solid before passing to `feature_boolean`.
- `surface_continuity` — query or enforce C0/C1/C2 / G0/G1/G2 on a surfacing node.
