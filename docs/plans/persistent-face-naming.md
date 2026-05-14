# Persistent face naming (design doc)

**Status:** planned · CAD-literature "Phase 4" topological naming problem.
**Owner:** TBD (sonnet agents per task).
**ROADMAP row:** see `🔮 Persistent face naming (topological IDs)` near the
bottom of the table.

## Why

Today every face reference in Kerf is a **positional integer** —
`TopExp_Explorer(shape, TopAbs_FACE)` walks faces in OCCT's internal order
and the Nth face gets id `N`. The OCCT worker emits a `faceIds: Uint32Array`
(per-triangle) plus a `faceMeta: [{id, planar, …}]` array keyed on that
integer, and `faceById(oc, shape, id)` reverse-resolves the integer back
into a `TopoDS_Face` on every re-eval.

The integer changes if **anything** upstream changes the explorer order:

- Adding a vertex to the upstream sketch.
- Adding / removing / reordering a `.feature` node.
- Switching a sketch from a single closed loop to multi-loop.
- Any boolean op that introduces or removes a face.
- Reordering the patterned instances of a `LinearPattern` / `PolarPattern`.

The user's stored intent (`target_face_id: 3`) silently refers to a
**different** face on the next evaluation. The user does not get a "face not
found" error in most cases — face id 3 exists, it's just the wrong face.
Push-pull suddenly pulls a hole inside-out; `cut_from_sketch` cuts through
the wrong wall; the draft on a `boss_with_draft` slopes the wrong direction.

This is the documented Phase 4 work the existing code already calls out:

- `src/lib/occtWorker.js:680` — *"Face-id stability caveat (mirrors push_pull):
  target_face_id is a post-evaluation snapshot index. Structural upstream
  edits can renumber faces. Phase 4 persistent-naming will fix this."*
- `src/lib/occtWorker.js:1140` — *"or the future face-id reference."*
- `src/components/FeatureRenderer.jsx:31-37` — *"ID-stability story: … the
  selection set is not persisted … a future polish would re-map by spatial
  proximity to keep 'intent' alive across edits."*
- `packages/kerf-cad-core/src/kerf_cad_core/feature_cut_from_sketch.py:21` —
  *"target_face_id is the post-evaluation face index … Phase 4 persistent-
  naming will fix this."*

## Concrete failure scenarios (from current code)

| Trigger | Affected feature | Symptom |
|---|---|---|
| User adds a segment to the base sketch | `feature_push_pull`, `feature_cut_from_sketch`, `feature_boss_with_draft` | Stored `target_face_id`/`face_id` now points at a neighbouring face. Push-pull goes the wrong way, cut subtracts from the wrong wall. |
| User inserts a fillet node before a cut | `feature_cut_from_sketch` | Fillet creates several new faces (the fillet surfaces). Side-face indices shift by ~N. Cut targets a fillet face → boolean fails OR cuts an unexpected region. |
| User edits sketch from single-loop to multi-loop | All face-anchored ops downstream | The cap face produced by extrude is the same intent, but its id changed because the side-face count grew. |
| Reorder `LinearPattern` instances | Any selection on a patterned instance | All ids shuffle; selection is silently re-pointed. |
| `feature_fillet` / `feature_chamfer` on edges from `target_edge_ids` | Edge analog of the same bug, same root cause (`edgeById` is positional). |
| `mateRefFromPick` mate refs (`{component_id, feature: 'face', feature_id: 'face-3'}`) | Constraints solve against a different face → assembly snaps to the wrong pose. |
| Imported STEP file re-exported & re-imported | All ops on that body | OCCT does not promise stable explorer order across STEP read trips. |

The mates feature (`packages/kerf-mates/`) shares the same pathology — its
refs are `face-N`-shaped strings (`src/lib/assembly.js::mateRefFromPick`).
The fix must extend there too, not just the `.feature` tree.

## Survey of naming schemes

### 1. Topological signature

Hash each face by its **adjacency pattern**:

- Count of bounding edges.
- Counts of incident vertices (by valence).
- Surface type (plane / cylinder / cone / sphere / torus / B-spline).
- Hashes of neighbour faces (recursive, fixed depth — typically 1 or 2).
- For each bounding edge: edge type (line / circle / B-spline) + endpoint
  vertex valences.

Robust under renumbering. Survives most local edits because adjacency is a
local invariant. The classical scheme used in Solidworks, NX, Onshape (and
the FreeCAD topo-naming refactor effort — *"Realthunder branch"*).

**Pros**: works on arbitrary shapes (no need for a producing sketch).
Survives most edits.

**Cons**: collisions on symmetric shapes (a cube has 6 indistinguishable
faces under any pure topological hash). Needs a tie-breaker. Sensitive to
boolean ops that genuinely change adjacency. Hard to debug — "face
`a4b91c33`" is opaque.

### 2. Sketch-anchored naming

For faces *derived from a sketch*, name them by the **sketch entity** that
produced them. Side faces of an extrude get one name per source sketch edge:

```
Pad-A.Side.Seg-3            // side face from segment 3 of the base sketch
Pad-A.TopCap                // cap face on the +normal side
Pad-A.BottomCap             // cap face on the −normal side
Pad-A.Side.Arc-1.0          // when one sketch arc produces multiple faces
```

Stable as long as **the sketch entity ids are stable**, which Kerf already
guarantees: planegcs entity ids are `seg-0`, `seg-1`, … assigned at
creation and persisted in the `.sketch` JSON. Adding `seg-7` doesn't
renumber `seg-3`.

**Pros**: ~70 % of common `.feature` faces are sketch-derived (any extrude /
revolve / sweep / loft / pocket / hole / boss). Names are **human-readable
and debuggable**. Survives all the ROADMAP-table scenarios except STEP
imports.

**Cons**: doesn't cover faces with no upstream sketch — STEP imports, NURBS
surface results, blend faces, boolean-cut boundary faces.

### 3. Geometric signature

Hash by **centroid + normal + area** (rounded to a sub-mm grid). Quick to
compute; survives renumbering.

**Pros**: cheap, no graph traversal.

**Cons**: fragile under any rigid transform of the part — translate the body
1 mm and every name changes. Useless for parametric edits where dimensions
move faces around. Only sensible as a *last-resort tie-breaker* inside the
topological hash, not as a primary scheme.

### 4. Hybrid (chosen)

Combine the strengths of (1) and (2):

- **Primary:** sketch-anchored where the face has a sketch lineage.
- **Fallback:** topological signature for free-floating faces (imports,
  NURBS, blend faces, boolean boundary faces).
- **Tie-break (collisions only):** geometric signature on the centroid.

This is what Onshape and (the in-flight) FreeCAD topo-naming use in
practice. SolidWorks' "Topology Manager" is roughly the same shape.

## Chosen scheme

> **Sketch-anchored primary + topological-signature fallback,
> human-readable.**

### Naming grammar

Every face gets a `name: string` field in the worker output alongside the
existing positional `id`. Names are dotted, human-readable identifiers:

```
<feature_id>.<role>[.<sketch_entity_id>][.<branch>][@<instance>]
```

Examples:

| Source | Name |
|---|---|
| Cap of `Pad-A` on +normal side | `Pad-A.TopCap` |
| Cap of `Pocket-B` on +normal side | `Pocket-B.TopCap` |
| Side face of `Pad-A` from `seg-3` | `Pad-A.Side.seg-3` |
| Side face from arc that produced 2 faces | `Pad-A.Side.arc-1.0`, `.1` |
| Revolve side face from segment | `Rev-C.Side.seg-2` |
| Revolve axis caps (if not full 360°) | `Rev-C.StartCap`, `Rev-C.EndCap` |
| Pattern instance 4 of `Pad-A.TopCap` | `LinPat-D.4/Pad-A.TopCap` |
| Mirror image of `Pad-A.TopCap` | `Mir-E.mirror/Pad-A.TopCap` |
| Boolean-cut boundary face | `Cut-F.boundary/<topohash:8>` |
| Fillet face on edge `Pad-A.Edge.seg-3` | `Fil-G.fillet/<topohash:8>` |
| STEP-imported face | `imp-<file_id:6>/<topohash:8>` |

The grammar is **opaque to consumers** — the worker emits the string and
backend / frontend treat it as a string key. The structure is only relevant
to the worker emitter.

### Topological hash (fallback)

When a face has no sketch lineage, compute an 8-character signature:

```
SHA-256(
  surface_kind,                           // 'plane' | 'cyl' | … | 'bspline'
  num_outer_edges,
  sorted([edge_kind, … for each edge]),
  sorted([vertex_valence, … for each vertex]),
  sorted([neighbour_surface_kind, …])     // depth-1 only, sorted
).hex[:8]
```

The hash deliberately ignores absolute geometry (centroids, normals) so
that translating the part doesn't break names. The 8-character truncation
yields 32 bits of address space — enough that random collisions are
vanishingly rare on a single body, and the collision-resolution path below
covers the worst case.

### Collision resolution

Two faces hashing to the same `topohash` are tagged with a deterministic
disambiguator `:0`, `:1` based on the (sketch-entity-id, instance-index,
parent-name) tuple sorted lexicographically. This is fully deterministic
across re-evals, so the same collision resolves the same way every time.

### Why human-readable over hex

`Pad-A.Side.seg-3` is **debuggable** — a developer reading a `.feature`
file can immediately tell what face is referenced. The verbosity cost
(~25 bytes per ref vs 6 for `face-3`) is negligible in JSON files that
already average 5–50 KB. Hex hashes are reserved for the topological
fallback where there's no human meaning to surface.

## Migration strategy

### Field rename, not field replace

The `.feature` JSON schema gains a new field next to the existing integer:

```diff
 {
   "op": "cut_from_sketch",
-  "target_face_id": 3,
+  "target_face_name": "Pad-A.TopCap",
+  "target_face_id": 3,            // legacy fallback, kept for backwards compat
   …
 }
```

Both fields are written on every new commit. Old files (no `*_name`) keep
working via the legacy integer. New files always carry both. The
**dual-write window** lasts at least one full deprecation cycle; after that,
the integer becomes optional and we can drop the legacy lookup helper.

### Resolution order (worker)

`resolveFaceRef(prev, node)` resolves in this order:

1. If `target_face_name` is set and the name exists in the current
   evaluation's name table → return that face.
2. Else if `target_face_id` is set → fall back to `faceById(prev, id)`.
3. Else → error.

This means an existing `.feature` file (integer-only) continues to evaluate
exactly as it does today — the cap-face migration is **opportunistic**.

### Opportunistic upgrade on edit

When a feature is edited (any LLM tool that writes a face ref, or any
gumball / pick-mode commit), the editor:

1. Reads the current name table for the body at the moment of the edit.
2. Looks up the captured face by **its current name** (via the worker's
   live name table).
3. Writes both the new name and the new integer to the JSON node.

Net effect: as users edit their parts, the names propagate organically.
We never need a global one-shot rewrite. The legacy-id fallback path stays
healthy until the last `face-N` ref is overwritten.

### One-shot migration script (optional)

For users / workshop projects that haven't been edited in a while, a
`kerf migrate face-names` CLI (Python, runs against a local Postgres) walks
every `.feature` file, evaluates each, and writes the name for every
captured face id. This is **not on the critical path** — the opportunistic
upgrade above covers active projects.

## Worker contract changes

### New mesh-level field

`breptToMesh(oc, shape)` returns:

```diff
 {
   vertices, indices, normals,
   faceIds,    // Uint32Array (per-triangle face index, unchanged)
   faceMeta,   // [{id, planar, origin, normal, uDir, vDir, centroid,
+              //   name: string }]   // ← new
+  faceNames,  // Map<id, string>  (id ↔ name, two-way lookup)
   edgeSegs, edgeIds, edgeMap,
+  edgeNames,  // Map<id, string>   // analogous for edges
 }
```

`faceIds` (per-triangle integer) stays — it's how the renderer paints
faces. `name` is the **stable** identifier that flows into the JSON.

### New worker → eval pipeline

The worker evaluates the feature tree as today, but each `op*` handler now
**emits the name table** for its output shape. Names are computed once at
shape construction (when we know the sketch lineage / boolean parentage)
and stored in a `WeakMap<TopoDS_Shape, Map<faceTShape, name>>` keyed by the
TShape pointer — that pointer is the closest thing OCCT gives us to a
"persistent identity" for a face within a single eval.

At mesh-build time (`breptToMesh`), the explorer walks faces, looks up
each by TShape pointer, and writes the name into `faceMeta[i].name`.

For ops we don't yet teach to emit names (Phase 2 ops), the fallback is to
hash topologically — so the contract is **always** populated even before
every op is upgraded.

### `face_outline` message

`face_outline` currently takes `{ tree, sketches, faceId: number }`. It
gains an optional `faceName: string`. When both are present, name wins.

## Frontend impact

### Gumball + face-pick mode (`FeatureRenderer.jsx`)

Today `onFacePick(faceId: number, partId: string)`. The new shape:

```diff
- onFacePick(faceId, partId)
+ onFacePick({ id: number, name: string, partId: string })
```

`FeatureView.jsx`'s `onFacePicked` writes both `target_face_name` and
`target_face_id` into the active feature node — see "Opportunistic upgrade
on edit" above. The selection set in `featureSelection.faceIds` continues
to use the `partId|faceId` integer string (it lives one render frame; the
name is only persisted on commit).

### Renderer hit-test

Hit-testing returns the integer (as today). The integer is resolved against
the worker's name table just before persisting. The renderer doesn't need
to know about names — they're a stamp-at-commit detail.

### Mate refs (`src/lib/assembly.js::mateRefFromPick`)

The `feature_id` field becomes a **name** (a string like `Pad-A.TopCap`)
rather than `face-3`. The mates solver consumes the same `faceNames` map,
or falls back to the legacy `face-N` lookup. Same dual-write story as the
`.feature` schema.

## Per-op risk matrix

| Op | Risk | Notes |
|---|---|---|
| `feature_pad`, `feature_revolve` | **low** | Pure sketch-anchored. T1 covers. |
| `feature_pocket` | **low** | Sketch-anchored. T1. |
| `feature_push_pull` | **low** | Same face as input; pass-through name. |
| `feature_cut_from_sketch` | **medium** | Boolean Cut: result has faces from both inputs + new boundary faces. T3. |
| `feature_boss_with_draft` | **medium** | Side faces still sketch-anchored; draft modifies geometry but preserves topology. T1 should handle. |
| `feature_fillet`, `feature_chamfer` | **medium-high** | Replaces the filleted edges with new faces. The new fillet face has no sketch lineage → falls back to topological. T2 + T3. |
| `feature_shell` | **medium** | Removes faces, adds inner shell faces. Removed faces' names are gone; inner faces are new. Topological fallback. T2. |
| `feature_sweep1/2`, `feature_loft` | **medium** | Side faces map to sweep rails / loft sections — extend the sketch-anchored scheme to "rail entity id". T1.5 (sub-task of T1). |
| `feature_network_srf`, `feature_blend_srf` | **medium** | NURBS surfaces with no straightforward lineage. Topological fallback. T2. |
| `feature_hole`, `feature_hole_pattern_from_sketch` | **low** | Each hole has a sketch-point lineage. Pattern instances get an `@N` suffix. T1 + T3. |
| `LinearPattern`, `PolarPattern`, `MirrorPattern` | **medium** | Each duplicated face inherits the source name with an instance suffix. T3. |
| `feature_helix`, `feature_rib`, `feature_multi_transform` | **medium** | Same shape as their non-patterned analogs. T1 + T3. |
| STEP / 3DM imports | **high (low fix cost)** | No lineage available → all faces get topological names. T2. The hash is stable across re-evals of the same file but not across re-imports. |
| `feature_draft` (standalone) | **medium** | Same body, draft just tapers — names pass through. T1. |

## Task breakout (sonnet-sized, with dependencies)

| ID | Task | Depends on | Effort | Notes |
|---|---|---|---|---|
| **T1** | Worker face-name emitter (sketch-anchored, base ops: extrude / revolve / cap / side faces). Adds `name` to `faceMeta`, builds `WeakMap<TShape, name>` per op, threads it through `breptToMesh`. | — | 1 day | Covers `feature_pad` / `feature_pocket` / `feature_revolve` and the 70 % case. |
| **T1.5** | Extend T1 to sweep1 / sweep2 / loft side-face naming (rail entity id + section index). | T1 | 0.5 day | Smaller because the plumbing already exists from T1. |
| **T2** | Topological-signature fallback hash. Implements `topoHash(face)` and uses it for faces with no sketch lineage. Wires the collision-disambiguator. | T1 | 1 day | Pure helper + tests. |
| **T3** | Pattern + boolean + fillet/chamfer face-name propagation. Linear/polar/mirror inherit source names with `@N`. Boolean ops tag boundary faces. Fillets/chamfers use topohash. | T1, T2 | 1 day | The fiddly one. Heavy on unit tests for each pattern type. |
| **T4** | Frontend face-id consumer migration. Gumball + pick-mode emit `{id, name, partId}`. `FeatureView.onFacePicked` dual-writes both fields. `FeatureRenderer` selection-set unchanged (still integer keys per-frame). | T1 | 0.5 day | Mechanical refactor. |
| **T5** | Backend schema migration. Add `target_face_name` / `face_name` fields to `feature_cut_from_sketch`, `feature_push_pull`, `feature_boss_with_draft`, `feature_fillet`, `feature_chamfer`, `feature_hole_pattern_from_sketch`. LLM tool schemas updated to accept names. Backwards-compat lookup helper. Mate-ref dual-write. | T1, T4 | 1 day | Touches every face-consuming feature module + `kerf-mates`. |
| **T6** | Migration of existing `.feature` files. Opportunistic on-edit (covered by T4/T5) + optional one-shot script `kerf migrate face-names` under `packages/kerf-core/scripts/`. | T1, T5 | 0.5 day | The opportunistic path is "free" — the explicit script is a polish item. |
| **T7** | Test coverage. Vitest: every op + every pattern type. Pytest: schema migration + backwards-compat lookup. Property-based: add a segment to a sketch, assert face name on cap is unchanged. | T1–T6 | 1 day | Property-based testing is the most valuable — it catches the silent-renumber bug head-on. |

**Total: ~5.5 sonnet-agent-days.**

Order of work: T1 → T1.5 / T2 in parallel → T3 → T4 / T5 in parallel → T6
→ T7.

## Open questions to resolve before implementation starts

1. **Naming canonicalisation for boolean boundary faces.** When `Cut-F`
   subtracts a cutter that shared a sketch with the target, the boundary
   face has *two* possible parents. Do we prefer the cutter's lineage, the
   target's lineage, or compose `Cut-F.boundary/<targetName>+<cutterName>`?
   The composed form is unambiguous but verbose. Affects T3. **This is the
   highest-risk question** — it's where SolidWorks' Topology Manager and
   Onshape's "Part Studio" make different calls and where the FreeCAD
   topo-naming branch has thrashed for years.

2. **OCCT TShape pointer stability within one eval.** We're relying on
   `TopoDS_Face::TShape().get()` being stable for the lifetime of a single
   shape graph. opencascade.js builds may delete intermediate shapes; we
   need to verify with a smoke test before T1 lands. Mitigation: copy the
   name into `faceMeta` at mesh-build time and discard the WeakMap.

3. **Sketch-edge id stability across edits.** Planegcs entity ids are
   stable today, but the sketcher v2 ops (`trim`, `extend`, `fillet`)
   might re-emit segments with fresh ids. Need an audit pass on
   `src/lib/sketchOps.js` before T1.

4. **Backwards-compat sunset.** When can we drop `target_face_id` from
   schemas? Suggestion: **never** — the dual-write cost is one integer per
   face ref. The legacy fallback is the migration safety net.

5. **STEP re-import naming.** Topohash is stable for one STEP file, but
   re-importing the same STEP after the upstream tool re-saved it can
   shuffle TShapes. Is that acceptable? Probably yes — STEP imports are a
   leaf case and users re-pick on re-import. Worth confirming with one
   workshop user before T2 ships.

6. **Mate-ref schema.** The existing mate `feature_id` is a string. Today
   it's `"face-3"`. After the migration it's `"Pad-A.TopCap"`. Mate
   solvers need to resolve the new string against the body's name table.
   The bigger lift is **deciding whether mate refs migrate opportunistically
   (same as `.feature` files) or get a one-shot rewrite**. Probably
   opportunistic, but assembles re-solving daily makes the opportunistic
   window short.
