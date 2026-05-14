# Face + edge gumballs (direct manipulation)

The gumball is the FeatureView's direct-manipulation handle: when the
user picks a face or edge in a `.feature` file's 3D viewport, a small
THREE.js widget attaches at the centroid. Drag → release commits a new
node onto the feature timeline. It's the SketchUp-style "grab the face
and pull" feel grafted onto our parametric tree.

The gumball doesn't have its own JSON file. It reads from the
workspace store's `featureSelection` and writes to the `.feature` file
via the same `updateFeature` helper the FeatureView panel uses. So
this doc is mostly a map between **what the user drags** and **which
feature node lands** — useful when the user describes a gesture and
asks the LLM to "do that without dragging".

## `featureSelection` shape

The store keeps two Sets of opaque keys (see
`src/store/workspace.js`):

```js
featureSelection: {
  faceIds: Set<"<partId>|<faceId>">,    // e.g. "p1|7"
  edgeIds: Set<"e<partId>|<edgeId>">,   // e.g. "ep1|12"
}
```

Face keys have **no** prefix; edge keys are prefixed with `e` so the
two sets can coexist without collision. Both partId and faceId/edgeId
are integers from the OCCT tessellation. Keys round-trip via
`parseEdgeKey` / direct split — there's no public helper to parse face
keys (they're just `partId|faceId`).

The gumball renders only when **exactly one** face or edge is
selected; multi-select disables it. The LLM can read this Set to
report what's currently picked, but mutating it directly is rare —
prefer the FeatureView's pick mode helpers when changing selection.

## Face gumball — translate + rotate

Three colored translate arrows and three rotate rings pinned at the
face centroid:

| Handle      | Color | Drag axis           | Commits feature node          |
|-------------|-------|---------------------|-------------------------------|
| Arrow X     | red   | world +X            | `push_pull` (distance projected onto face normal) |
| Arrow Y     | green | world +Y            | `push_pull`                   |
| Arrow Z     | blue  | world +Z            | `push_pull`                   |
| Ring around X | red | rotation about world X | `rotate_face` (axis_local: `u`) |
| Ring around Y | green | rotation about world Y | `rotate_face` (axis_local: `v`) |
| Ring around Z | blue  | rotation about world Z | `rotate_face` (axis_local: `normal`) |

### `push_pull` — drag a face along its normal

```json
{
  "id": "push_pull-1",
  "op": "push_pull",
  "face_id": 7,
  "distance": 5.0
}
```

The translate handles are world-XYZ but the OCCT op is defined
**along the face normal**. Gumball commits
`distance = world_delta · face_normal`, so dragging an axis-aligned
face's red arrow by 5 mm with the face normal pointing along +X
commits `distance: 5`. A tilted face degrades by the cosine of the
angle between the dragged world axis and the face normal — that's
expected.

The 0.05 mm dead-zone in `Gumball.jsx` rejects accidental clicks; if
the LLM wants a tiny adjustment, write the node directly via
`edit_file` rather than relying on the gumball's gesture vocabulary.

### `rotate_face` — drag a ring

```json
{
  "id": "rotate_face-1",
  "op": "rotate_face",
  "face_id": 7,
  "angle_deg": 12.5,
  "axis_local": "normal"
}
```

`axis_local` is `"normal"` (default), `"u"`, or `"v"` — the OCCT
worker resolves these against the face's local frame. The screen
ring the user dragged maps as in the table above. 0.5° dead-zone.

## Edge gumball — single radial fillet handle

A single 1D radial handle at the edge midpoint, perpendicular to the
edge. Drag → live amber preview ring at radius `r`; release commits:

```json
{
  "id": "fillet-1",
  "op": "fillet",
  "edge_filter": "manual",
  "edge_ids": [12],
  "radius": 1.5
}
```

The radial direction is `cross(edgeAxis, cameraForward)` — see
`computeRadialBasis`. When the camera orbits, the gumball
re-orients per-frame so the handle always sticks to the screen-plane
tangent. 0.05 mm dead-zone; the radius is clamped to ≥ 0.

### `projectScreenDeltaToRadialDistance`

The drag → world-distance projector is exported and unit-tested
(`src/__tests__/gumball.test.js`):

```js
projectScreenDeltaToRadialDistance(
  midWorld,        // [x, y, z]   — edge midpoint
  edgeAxisWorld,   // [x, y, z]   — unit edge direction
  camera,          // THREE.PerspectiveCamera
  dxPx, dyPx,      // pixel delta from drag-start
  viewportW, viewportH
)  // → world-units along the radial basis, clamped ≥ 0
```

Both the visible handle and the commit math go through this same
function, so the user always sees the radius they're committing.

## Inferring a gumball gesture from text

When the user describes a gesture, map it to a node and let the LLM
write it directly via `edit_file`:

| Phrase                                    | Node                           |
|-------------------------------------------|--------------------------------|
| "push this face out 5 mm"                 | `push_pull`, distance=5        |
| "pull the face 3 mm into the part"        | `push_pull`, distance=-3       |
| "tilt the face 10 degrees around its normal" | `rotate_face`, angle_deg=10, axis_local=`normal` |
| "fillet this edge with r=2"               | `fillet`, edge_ids=[N], radius=2 |

The LLM should resolve the face / edge ID from `featureSelection`
when exactly one is picked; otherwise ask the user to click.

## Known limits

- **One-at-a-time.** No multi-face / multi-edge gumball. The widget
  hides for empty selection, multi-selection, and mixed
  face+edge selection.
- **Translate is world-axis, not face-axis.** Push-pull along a
  tilted face uses the cosine projection — fine for the common case,
  awkward for a face at 45° to all three world axes. A future slice
  may add a face-aligned basis toggle.
- **Edge gumball is fillet-only.** No chamfer handle yet; for
  chamfer the user (or LLM) edits the feature tree directly.
- **Selection keys are opaque.** The `partId|faceId` shape is a
  rendering detail — don't synthesize keys; read what the
  FeatureRenderer wrote.
