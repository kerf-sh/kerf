# FreeCAD parity: sketch → 3D shortcuts (design doc)

**Status:** planned · breakout from the ROADMAP row of the same name.
**Owner:** TBD (sonnet agents per task).
**ROADMAP row:** see `🔮 FreeCAD parity: sketch → 3D shortcuts` plus the
`📋 next` sub-rows below it.

## Why

FreeCAD's PartDesign workbench lets a user pick a sketch and an "active body"
and apply a feature (boss / pocket / hole) in one click. Kerf's existing
`.feature` workflow needs more clicks per operation — the user authors a
`pad` *and* a `feature_draft` separately when they want a drafted boss; an
array of identical holes is N hand-written `hole` nodes; and the loft / sweep
modes most jewellery + thin-walled mechanical work needs (mid-plane symmetric
loft, tangent-locked sweep) are buried as edge-case flags rather than
first-class moves.

These five shortcuts collapse the per-operation step count so a Kerf user
doing PartDesign-style work has the same "sketch → click → done" rhythm a
FreeCAD user does.

| # | LLM tool | Behaviour |
|---|---|---|
| 1 | `feature_boss_with_draft` | Pad + draft in one node. |
| 2 | `feature_cut_from_sketch` | Sketch-region subtraction normal to any planar face. |
| 3 | `feature_hole_pattern_from_sketch` | One `hole` per point entity in a sketch. |
| 4 | (flag on `feature_loft`) | `symmetric: true` → mid-plane symmetric loft. |
| 5 | (flag on `feature_sweep1`) | `mode: "corrected_frenet"` exposed end-to-end (tangent-locked frame). |

The last two are **flag extensions on existing tools**, not new tools. The
worker already accepts a `mode` arg on `feature_sweep1` (auto / frenet /
corrected_frenet); the work is wiring the symmetric-loft path and ensuring
the LLM doc + FeatureView inspector expose both knobs.

## Audit findings

**Backend.** Feature-author tools live in
`packages/kerf-imports/src/kerf_imports/tools/feature_*.py`. Each follows the
same shape: a `ToolSpec` declaring the input schema, an `async def
run_feature_*` handler that validates args + calls
`kerf_cad_core.surfacing.append_feature_node` to add a JSON node to the
target `.feature` file. The backend tool **does not run OCCT** — it only
writes the timeline node. Geometry evaluation happens in the browser via
`src/lib/occtWorker.js`.

Surfacing-tier tools (`feature_sweep1`, `feature_sweep2`, `feature_loft`,
`feature_network_srf`, `feature_blend_srf`) live in
`packages/kerf-cad-core/src/kerf_cad_core/surfacing.py` for historical
reasons — that split is fine; the new tools will go alongside the existing
PartDesign feature tools under `kerf-imports/.../tools/`.

**Worker.** `src/lib/occtWorker.js` is the single evaluator. The dispatcher
is a `switch (node.op)` near line 940. Today it handles: `pad, pocket,
revolve, fillet, chamfer, shell, hole, linear_pattern, polar_pattern,
mirror_pattern, push_pull, sweep1, sweep2, network_srf, blend_srf, loft,
variable_radius_fillet`. Notably **`draft`, `helix`, `rib`, `mirror`,
`multi_transform` are written by the backend tools but the worker has no
handler for them** — they sit dormant in the JSON. Any work that adds a new
op needs a matching worker case or it does nothing visible.

Helper utilities the worker already exposes for free:

- `faceForSketchPath`, `wireForSketchPath` — sketch → planar face / wire.
- `sketchToGeom2`, `geom2ToWire` — pure-JS sketch → JSCAD Geom2 → wire.
- `faceById`, `edgeById`, `faceFrame` — index lookups + planar frame.
- `placeFaceOnPlane`, `placeWireOnPlane` — orient geometry on the sketch's
  declared plane (XY / XZ / YZ / face-anchored).
- `BRepPrimAPI_MakePrism_1` (already used by `pad` / `pocket`), the
  `BRepAlgoAPI_Cut_3` / `Fuse_3` pair (booleans), `BRepFilletAPI_MakeDraft`
  is *not* yet imported but is in the OpenCascade.js binding.

**Frontend.** `src/components/FeatureView.jsx` owns the `FEATURE_KINDS`
catalog (lines 64–301) — each entry declares an icon, default param values,
and the inspector field schema. The Add-feature popover (line 907) groups
ops into four categories: `sketch / modify / pattern / surface`. The new
shortcuts belong in `sketch`. The inspector field kinds (`sketch_picker`,
`feature_picker`, `face_picker`, `face_picker_single`, `number`, `select`,
`bool`, `sketch_path_list`) cover every input these shortcuts need; no new
field kinds are required.

**LLM docs.** `packages/kerf-chat/llm_docs/feature.md` is the canonical
catalog of feature-tree operations. Per-op deep dives live in either the
chat-package docs or `kerf-imports/llm_docs/feature_*.md` (e.g. helix). New
shortcuts get a section in `feature.md` plus a dedicated worked-examples
doc under `kerf-imports/llm_docs/`.

**Sketch model.** A `.sketch` is JSON with `entities: [{type, ...}]`. Point
entities are `{type:'point', id, x, y}`. The hole-pattern shortcut leans on
the existing point entity directly — no schema change.

## Per-shortcut design

### 1. `feature_boss_with_draft`

**Intent.** Single tool: sketch + height + draft angle + neutral plane →
solid that's the padded body with the draft taper baked in. Replaces the
pad + face-id-picking + `feature_draft` two-step.

**OCCT pathway.** Two viable approaches:

1. **`BRepFeat_MakePrism` with `Draft` mode** — the "fused" approach. One
   call produces the drafted prism in one shot. Cleaner, but the
   OpenCascade.js binding for `BRepFeat_MakePrism`'s draft-angle overload
   is patchy; needs probing at the binding layer.
2. **`BRepPrimAPI_MakePrism` then `BRepOffsetAPI_DraftAngle`** — pad first,
   walk all side faces of the resulting prism, apply per-face draft via
   `BRepOffsetAPI_DraftAngle`. More reliable across binding versions; this
   is the v1 path. The fallback when the binding has the `Draft` overload
   missing is also this path, so we ship it directly.

Recommended path: **(2) explicit two-stage** — write a small helper
`opBossWithDraft(oc, _prev, node, sketches, tracker)` that:

```text
1. faceForSketchPath → planar face on sketch plane.
2. Compute extrusion vector (height * direction * normal) — same logic as opPad.
3. BRepPrimAPI_MakePrism → prism solid.
4. Walk side faces (TopExp_Explorer FACE, skip top + bottom face by normal-vs-axis dot).
5. BRepOffsetAPI_DraftAngle(prism); for each side face Add(face, normal, draft_rad, neutral_plane).
6. Build, IsDone, return.
```

The neutral plane defaults to the **sketch plane** — that's where the
profile is undistorted. (FreeCAD calls this the "base feature".)

**Schema.** Stored node:

```json
{
  "id": "boss-1",
  "op": "boss_with_draft",
  "sketch_path": "/profile.sketch",
  "height": 10,
  "direction": "up",
  "draft_angle_deg": 3,
  "draft_direction": "outward"
}
```

`direction` matches `pad` (`"up" | "down" | "symmetric"`). `draft_angle_deg`
clamped to `[-30, 30]` (same as `feature_draft`). `draft_direction`
`"outward"` widens away from the sketch plane, `"inward"` narrows toward it.

**Edge cases.**

- `draft_angle_deg = 0` → degenerates to a plain pad. Acceptable; emit a
  warning hint, don't error.
- `|draft_angle_deg| > 30` → BAD_ARGS (matches `feature_draft`).
- Sketch produces no planar face → NOT_FOUND.
- Draft overhangs and produces self-intersection (too-steep angle for
  height + profile aspect) → OCCT's `IsDone()` returns false; surface as
  `OCCT_BUILD_FAILED` with a hint "try a smaller angle".
- Open-profile sketch → fall through to `pad`'s "open profile" behaviour
  (current pad doesn't formally reject these; we don't introduce a new
  fail mode here).

**Frontend wiring.** New `FEATURE_KINDS` entry in `FeatureView.jsx`:

```js
{
  op: 'boss_with_draft',
  label: 'Boss + draft',
  icon: Box,          // re-use Box; can swap to Cone later
  defaults: { sketch_path: '', height: 10, direction: 'up',
              draft_angle_deg: 3, draft_direction: 'outward' },
  fields: [
    { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
    { key: 'height', kind: 'number', label: 'Height (mm)', min: 0.001 },
    { key: 'direction', kind: 'select', label: 'Direction',
      options: [/* up/down/symmetric */] },
    { key: 'draft_angle_deg', kind: 'number', label: 'Draft angle (°)',
      min: -30, max: 30 },
    { key: 'draft_direction', kind: 'select', label: 'Draft direction',
      options: [
        { value: 'outward', label: 'Outward (widen away from sketch)' },
        { value: 'inward',  label: 'Inward (narrow toward sketch)' },
      ] },
  ],
}
```

Slot it into `FEATURE_CATEGORIES.sketch` right after `pad`.

**Tests.**

- pytest `test_feature_boss_with_draft.py` — schema validation; node-append
  smoke; draft-angle clamp (`-30 / 0 / +30 / 35 → BAD_ARGS`); missing-args
  smoke.
- vitest `occtWorker.boss.test.js` — load a 50×50 square sketch, run
  `boss_with_draft` with `height=20, draft_angle_deg=10`, assert the top
  face is smaller than the bottom face (signed area ratio).

---

### 2. `feature_cut_from_sketch`

**Intent.** Subtract a sketched region from a planar face of an existing
body. Today's `pocket` extrudes through the **sketch plane**, not normal
to an arbitrary face. The new tool lets the LLM cut a slot in the side of
a part without rebuilding the sketch on that face first.

**OCCT pathway.**

```text
1. face = faceById(prev, target_face_id) → planar face.
2. frame = faceFrame(face) → origin + normal of the face.
3. faceForSketchPath → planar face from the sketch (in its own plane).
4. Re-orient that profile face onto the target face's frame:
     placeFaceOnPlane(sketch_face, {type:'face_anchored', frame})
5. vec = -normal * depth (cut INTO the body).
6. tool = BRepPrimAPI_MakePrism(reoriented_face, vec).
7. cut = BRepAlgoAPI_Cut_3(prev, tool).
```

`placeFaceOnPlane` already accepts a face-anchored plane spec (the worker's
push-pull / sketch-on-face plumbing uses it). No new helper needed.

**Schema.**

```json
{
  "id": "cut-1",
  "op": "cut_from_sketch",
  "target_id": "pad-1",
  "target_face_id": 7,
  "sketch_path": "/slot.sketch",
  "depth": 4,
  "reverse": false
}
```

`target_face_id` is the post-eval face index (same convention as
`push_pull`). `reverse: true` flips the cut direction (along `+normal`
instead of `-normal`) so the same node can cut from either side without
re-picking the face.

**Edge cases.**

- Target face is non-planar → BAD_ARGS (worker checks `frame.planar`).
- `target_face_id` out of range → NOT_FOUND.
- Cut depth > body thickness → boolean produces a valid through-cut; no
  error needed (this is the desired behaviour for through-slots).
- Sketch produces no closed loop → NOT_FOUND from `faceForSketchPath`.
- Face id stability — `cut_from_sketch` shares `push_pull`'s "snapshot"
  weakness (re-eval after upstream structural edits may rebind the face).
  Document this in the LLM doc, mirror `push_pull`'s caveat.

**Frontend wiring.** `FEATURE_KINDS` entry; slot after `pocket`.

```js
{
  op: 'cut_from_sketch',
  label: 'Cut from sketch',
  icon: Disc,
  defaults: { target_id: '', target_face_id: -1, sketch_path: '',
              depth: 5, reverse: false },
  fields: [
    { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
    { key: 'target_face_id', kind: 'face_picker_single', label: 'Face' },
    { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
    { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
    { key: 'reverse', kind: 'bool', label: 'Reverse direction' },
  ],
}
```

`face_picker_single` already exists (used by `push_pull`).

**Tests.**

- pytest `test_feature_cut_from_sketch.py` — schema + node-append, missing
  args, negative depth.
- vitest — build a cube via `pad`, pick face id=3 (the +X face), run
  `cut_from_sketch` with a 5 mm circle profile, depth=3, assert the
  result's bounding box on +X is unchanged but the body has a hole on
  that face (vertex-count delta > threshold).

---

### 3. `feature_hole_pattern_from_sketch`

**Intent.** A sketch carrying N point entities (`{type:'point', x, y}`) →
N `hole` features with shared diameter / depth params. The user draws one
sketch with the hole locations and gets a parametric hole-grid for free.

**OCCT pathway.** Two strategies:

1. **Expand-on-write** — the backend tool emits N individual `hole` nodes,
   one per point. The worker doesn't need any new handler. **Cheap to
   ship; pattern is non-parametric (changing the sketch doesn't auto-
   update the holes).**
2. **New `hole_pattern` op** — the backend emits ONE node referencing the
   sketch path; the worker walks the sketch's point entities at eval-time
   and runs N cuts. **More work but parametric** — re-sketching the
   pattern re-evaluates.

Recommendation: **(2) parametric `hole_pattern` op**. The eval cost is
small (one boolean per point on the same body), and parametric behaviour
matches the rest of the feature timeline. A v1 shortcut that's the only
non-parametric op in the tree would be a wart.

Worker handler:

```text
opHolePattern(oc, prev, node, sketches, tracker):
  points = parseSketchPoints(node._sketches[node.sketch_path])
    // returns [{x, y}, ...] of type='point' entries skipping 'origin'
  if (points.length === 0) throw 'no point entities'
  let body = prev
  for each (x, y) in points:
    body = cutCylinder(body, x, y, node.diameter, node.depth, sketch.plane)
      // factored out of opHole — same primitive
  return body
```

Pull the cylinder-cut block out of `opHole` into a helper
`cutCylinderAtPoint(oc, body, x, y, dia, depth, plane, tracker)` and have
both `opHole` and `opHolePattern` call it. Hole's "first circle in sketch
wins, else first non-origin point" stays — `opHolePattern` just iterates
points.

**Schema.**

```json
{
  "id": "hpat-1",
  "op": "hole_pattern",
  "target_id": "pad-1",
  "sketch_path": "/hole-grid.sketch",
  "diameter": 3,
  "depth": 8,
  "countersink_diameter": 0,
  "countersink_depth": 0
}
```

`countersink_*` are optional. When non-zero, each cut is a stepped
cylinder (cylinder of `countersink_diameter` for `countersink_depth`,
then `diameter` for `depth`). v1 can skip these — bare cylinder cut only
— and add countersink as a follow-up patch. **Decision: ship v1 without
countersink; surface the schema slots as `"reserved"` so an LLM doesn't
guess.**

**Edge cases.**

- Sketch has zero point entities → BAD_ARGS with hint "sketch must contain
  point entities (use `sketch_add_entity` with `type:'point'`)".
- Sketch has non-point entities mixed in → ignore them silently (so the
  user can draw construction circles as visual references); document
  this.
- Diameter > local body wall thickness — same as `hole`; boolean produces
  a through-hole. No error.
- All points coincide → still N cuts (operationally a no-op after the
  first); not worth special-casing.

**Frontend wiring.** `FEATURE_KINDS` entry after `hole`:

```js
{
  op: 'hole_pattern',
  label: 'Hole pattern',
  icon: Drill,
  defaults: { target_id: '', sketch_path: '', diameter: 3, depth: 5 },
  fields: [
    { key: 'sketch_path', kind: 'sketch_picker', label: 'Points sketch' },
    { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
    { key: 'diameter', kind: 'number', label: 'Diameter (mm)', min: 0.001 },
    { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
  ],
}
```

**Tests.**

- pytest `test_feature_hole_pattern_from_sketch.py` — schema + node-append;
  reject missing args.
- vitest — sketch with 4 point entities in a square, pad a 50×50×10
  block, run `hole_pattern` with diameter=3 depth=5; assert resulting
  mesh has 4 cylindrical voids (vertex count delta ≈ 4× the `hole`
  delta).

---

### 4. Symmetric loft (`feature_loft` flag)

**Intent.** Loft between two sketches that's symmetric about their mid-
plane. Useful for thin-walled symmetric shells (handles, mounting brackets,
ergonomic grips) where the user wants to draw one side and have the other
implied.

**OCCT pathway.** No new builder. Computational sequence:

```text
1. Read both profile sketches.
2. Compute mid-plane = average of the two plane frames (origin midpoint,
   averaged normal). Sketches assumed coplanar parallel or with parallel
   normals; reject non-parallel normals as BAD_ARGS.
3. Mirror sketch[0] across mid-plane → sketch[0]' on the other side of mid.
4. Mirror sketch[1] across mid-plane → sketch[1]' on the other side of mid.
5. Run ThruSections(sketch[0], sketch[1], sketch[1]', sketch[0]')
   in that order to get a symmetric closed loft. (NOTE the order: original
   pair + mirrored pair reversed produces a symmetric solid.)
```

Alternative — when both inputs are coplanar (degenerate mid-plane case),
the symmetric option degenerates to a single revolve about the symmetry
axis. v1 rejects this case (BAD_ARGS); the user should use `revolve`
directly.

Worker: extend `opLoft` to honor `node.symmetric`. When true, expand the
profile list per the mirroring rule above before passing to
`BRepOffsetAPI_ThruSections`.

**Schema.** Existing `loft` node gets an optional flag:

```json
{
  "id": "loft-1",
  "op": "loft",
  "profile_sketch_paths": ["/p1.sketch", "/p2.sketch"],
  "ruled": false,
  "closed": false,
  "symmetric": true,
  "continuity": "C1"
}
```

`symmetric: true` requires `profile_sketch_paths.length === 2` (the
shortcut case). For ≥3 profiles we error with "symmetric mode requires
exactly 2 profiles".

**Edge cases.**

- Profiles not parallel-coplanar → BAD_ARGS "symmetric loft needs parallel
  sketch planes".
- Profiles identical → mid-plane sweep collapses to a thin shell; still
  valid, returns near-zero-volume body. No error; warn in console.
- `symmetric: true` + `closed: true` → contradictory (closed already wraps);
  BAD_ARGS.

**Frontend wiring.** Add a `bool` field to the existing `loft` kind:

```js
{ key: 'symmetric', kind: 'bool', label: 'Symmetric (mid-plane)' },
```

(slotted before `closed`).

**LLM tool.** No new tool — `feature_loft` (currently in
`packages/kerf-cad-core/src/kerf_cad_core/surfacing.py`) gets a
`symmetric` arg in its input schema. The handler writes the flag into the
emitted node; everything else is worker-side.

**Tests.**

- pytest — schema accepts `symmetric=true|false`; default false; rejects
  combo with `closed=true`.
- vitest — two identical 20 mm circle sketches at z=0 and z=20; symmetric
  loft. Expect bounding box centred on z=10, symmetric volume about z=10
  (volume above mid-plane == volume below within 1%).

---

### 5. Tangent-locked sweep (`feature_sweep1` mode plumbing)

**Intent.** Expose the existing `corrected_frenet` mode end-to-end so a
user can request a sweep whose section orientation tracks the path's
tangent (Frenet frame) without binormal flips that the default "auto"
mode picks. This is the right move for jewellery shanks, pipe coils, any
curved profile where the section must follow the curve faithfully.

**OCCT pathway.** Already implemented in the worker
(`src/lib/occtWorker.js::opSweep1`) — `mode === 'corrected_frenet'`
calls `pipe.SetMode_5(true)` when the binding exists. The work is
**not OCCT; it is end-to-end exposure**:

1. `feature_sweep1` backend tool already accepts no `mode` arg —
   `feature_sweep2` does, `feature_sweep1` doesn't. Add it.
2. `feature_sweep1`'s LLM doc and FeatureView inspector already mention
   the modes via `sweep2`. Reuse the same wording.
3. **Verify** the binding actually triggers when set — add a vitest that
   sweeps a square section along a coil and asserts the section
   orientation doesn't pop at the inflection (compare against `auto`
   mode's known-bad behaviour for that path).

**Schema.** `feature_sweep1` accepts:

```json
{ "mode": "auto" | "frenet" | "corrected_frenet" }
```

— matching `feature_sweep2`'s existing enum.

**Edge cases.**

- Path has zero curvature (a straight line) → Frenet frame is undefined.
  OCCT's `SetMode_5` falls back gracefully on this build. v1: pass
  through; if `IsDone` returns false we surface it as `OCCT_BUILD_FAILED`.
- Binding lacks `SetMode_5` → silently degrades to default Frenet. The
  worker already does this; document the degradation in the LLM doc.

**Frontend wiring.** `sweep1` kind's `fields` already has a `mode`
select... but it's missing! Check line ~220 of `FeatureView.jsx`:

```js
{ key: 'mode', kind: 'select', label: 'Mode', options: [
  { value: 'auto', label: 'Auto' },
  { value: 'frenet', label: 'Frenet' },
  { value: 'corrected_frenet', label: 'Corrected Frenet' },
] },
```

Already present. Confirm during implementation that the field shows up
and saves correctly — the worker honors the flag.

**Tests.**

- pytest — `feature_sweep1` accepts `mode`; validates enum; stores in
  node JSON.
- vitest — `corrected_frenet` mode on a known-twisty path produces a
  body whose section axis tracks `T̂(s)` (test by sampling cross-sections
  numerically; tolerance loose since OCCT binding behaviour varies).

---

## Reusable machinery

Cross-shortcut helpers worth factoring out:

- `cutCylinderAtPoint(oc, body, x, y, dia, depth, plane, tracker)` —
  factored from `opHole`; consumed by `opHole` and `opHolePattern`.
- `walkSideFaces(oc, prism, axisDir)` — used by `opBossWithDraft` to enumerate
  drafted faces. Can live in `occtWorker.js` next to `filterEdges`.
- `mirrorSketchAcrossPlane(geom2, plane)` — pure JS; consumed by the
  symmetric loft. Lives in `src/lib/sketchGeom2.js`.

**Shared backend pattern** — every new tool uses
`kerf_cad_core.surfacing.{next_node_id, read_feature_content, append_feature_node}`,
matching the existing `feature_helix` / `feature_rib` / `feature_draft`
style. No new abstraction.

## Dependency graph

```
Task A (worker plumbing: cutCylinderAtPoint refactor)
  └─> Task C (feature_hole_pattern_from_sketch)
Task B (worker plumbing: walkSideFaces helper)
  └─> Task D (feature_boss_with_draft)
Task E (feature_cut_from_sketch)           — independent
Task F (loft symmetric flag)               — independent
Task G (sweep1 mode flag through tool)     — independent
```

Tasks A and B are **infra-only refactors** (no behaviour change); they
can land first or as part of C/D respectively. Recommend: roll A into C
and B into D — each new tool brings its own helper.

Tasks C, D, E, F, G are otherwise mutually independent — five parallel
sonnet agents could pick them up.

## Open architectural questions

1. **Should boss_with_draft use `BRepFeat_MakePrism` (one-call) or
   `BRepPrimAPI_MakePrism + BRepOffsetAPI_DraftAngle` (two-call)?**
   We've chosen two-call for binding portability. Revisit if the binding
   gains stable `BRepFeat_MakePrism::Init` overloads — one-call is faster
   and gives cleaner topology.

2. **Hole pattern: parametric or expand-on-write?** Going parametric
   (new `hole_pattern` op). The alternative (emit N `hole` nodes from
   the backend tool) saves a worker handler but loses re-evaluation
   when the sketch changes — not worth the simplification.

3. **Cut-from-sketch face-id stability.** Same caveat as `push_pull` —
   structural edits to upstream features renumber faces. Phase 4's
   persistent-naming work will fix it; v1 documents the caveat.

4. **Symmetric loft for ≥3 profiles?** v1 limits to exactly 2. The
   ≥3-profile case is theoretically definable (mirror every profile,
   re-interleave) but the meaning is ambiguous — defer.

5. **Tangent-locked sweep test on `opencascade.js` builds that lack
   `SetMode_5`.** The worker degrades silently. We should surface this
   in `evalState` (a `degraded: true` flag in the worker message) so the
   FeatureView can show a hint. Not a blocker for this work but worth
   queuing as a separate polish item.

## Effort estimate

| Task | Sonnet-days | Notes |
|---|---|---|
| C — `feature_hole_pattern_from_sketch` | 1.0 | includes cutCylinder refactor |
| D — `feature_boss_with_draft` | 1.0 | includes walkSideFaces helper |
| E — `feature_cut_from_sketch` | 1.0 | face-anchored prism + boolean |
| F — Loft `symmetric` flag | 0.5 | one branch in opLoft + schema |
| G — Sweep1 `mode` flag end-to-end | 0.5 | tool arg + LLM doc |

**Total: 4.0 sonnet-agent-days** (5 tasks). With one agent per task, the
work parallelises to ≈1 wall-day. Sequential single-agent estimate: ≈4
working days inclusive of testing + LLM doc updates.
