# NURBS surfacing Phase 4 — full robustness

**Status:** Capabilities 1, 2, and 4 shipped. Capability 3 (matchSrf) deferred
pending persistent-face-naming (see Sequencing). Zebra / reflection-line
viewport toggle shipped (shader-side `ShaderMaterial` in `src/lib/zebraMaterial.js`
+ toggle in `src/components/Renderer.jsx`). Algorithmic G3 structurally deferred
(`GeomAbs_G3` absent in stock OCCT — confirmed). See status snapshot below.
**Owner:** imranparuk
**Companion docs:**
- [`nurbs-booleans-v1.md`](./nurbs-booleans-v1.md) — solid-cap path (shipped).
- [`nurbs-booleans-scoping.md`](./nurbs-booleans-scoping.md) — original
  scoping with the explicit "what we're NOT doing" list. **This plan is
  the materialised version of those deferred scopes.**

## Status snapshot

### What's shipped

- **Phase 4a (jewelry-priority surfacing)** — `sweep1`, `sweep2`,
  `network_srf`, `blend_srf`, `loft` ops + LLM tools + `surface_continuity`
  query/enforce tool covering C0/C1/C2 (sweeps/network) and G0/G1/G2
  (blend). See `src/lib/occtWorker.js::{opSweep1, opSweep2, opNetworkSrf,
  opBlendSrf, opLoft}` and `packages/kerf-cad-core/src/kerf_cad_core/surfacing.py`.
- **Phase 4b (gumball direct face manipulation)** — face translate +
  rotate handles commit `push_pull` / `rotate_face` nodes; edge gumball
  commits `feature_fillet`.
- **NURBS booleans v1 — solid-cap path (shipped)** — binding probe +
  `surfaceToSolid` helper + `opToSolid` worker handler + `feature_to_solid`
  LLM tool + `feature_boolean` LLM tool + inspector entries + tests. Plan:
  [`nurbs-booleans-v1.md`](./nurbs-booleans-v1.md). Surfaces → solid via
  `BRepBuilderAPI_Sewing` + `MakeSolid`, then `BRepAlgoAPI_Cut_3` / `Fuse_3`
  / `Common_3`.
- **Capability 1 (Robust NURBS-NURBS surface booleans) — shipped.**
  `feature_surface_boolean` in `surfacing.py` + `opSurfaceBoolean` worker
  handler. Accepts Face/Shell/Solid operands; returns compound of trimmed face
  fragments. `ShapeFix_Shape` pre-pass + `ShapeUpgrade_UnifySameDomain`
  cleanup; `fuzziness` + `coarse_mode` flags. Pure-Python guard layer in
  `geom/surface_boolean_robust.py`.
- **Capability 4 (G3 curvature-comb visualisation) — shipped.**
  `feature_surface_curvature_combs` in `surfacing.py` samples principal
  curvatures via `GeomLProp_SLProps`; Three.js `CurvatureCombOverlay.jsx`
  renders combs in-viewport. Algorithmic G3 enforcement structurally deferred
  (`GeomAbs_G3` absent from `GeomAbs_Shape` enum — confirmed).
- **P1-6 zebra / reflection-line viewport toggle — shipped.**
  `src/lib/zebraMaterial.js` — `THREE.ShaderMaterial` that reflects the view
  direction in the surface normal and projects onto a periodic stripe axis
  (classic parallel-tube environment-map simulation). "Zebra" button in the
  viewport top-right swaps every mesh to the zebra material and restores on
  toggle-off. No WASM rebuild required.
- **Capability 2 (Trim-by-curve) — pure-Python + worker wiring shipped.**
  `packages/kerf-cad-core/src/kerf_cad_core/geom/trim_curve.py` implements
  UV-space projection (`project_curve_to_uv`), face splitting (`split_face_uv`,
  `trim_face`), `TrimCurve` dataclass, and `@register` LLM tools
  `query_trim_curve_uv` / `validate_trim_curve`.  Worker side: `opTrimByCurve`
  in `src/lib/occtWorker.js` + `projectCurveOntoSurface` / `splitFaceAlongCurve`
  in `src/lib/occtBridge.js` (C2-T2/T3 complete).  LLM tool `feature_trim_by_curve`
  in `surfacing.py` + `_TOOL_MODULES` registration.  49 hermetic pytest cases
  in `packages/kerf-cad-core/tests/test_trim_curve.py` — all green.
  **WASM-blocked remainder:** `BRepFeat_SplitShape` and `BRepProj_Projection`
  binding presence is unconfirmed at runtime (C2-T1 probe not yet run on a live
  WASM build). The worker's `TrimByCurveUnsupportedError` fires if those classes
  are absent; escalate to C2-T12 (Section+prism fallback) if that occurs.

### What this plan covers

The four frontier capabilities the user identified as the remaining
Phase 4 work — explicitly deferred in both the scoping doc and v1 plan:

1. **Robust NURBS-NURBS booleans** — surface-on-surface intersection
   that does not require the solid round-trip, returning trimmed face
   fragments rather than refusing non-solid operands.
2. **Trim-by-curve** — split a face along a 3D curve's projection and
   keep one side.
3. **matchSrf** — adjust a surface's edge tangency / curvature to G1 or
   G2 match an adjacent surface's edge.
4. **G3 continuity** — extend `surface_continuity` to honour G3
   (curvature-of-curvature). Honesty up front: this is the riskiest of
   the four; OCCT exposure is unclear and may require a custom WASM
   rebuild OR a documented approximation path.

The multi-year framing on the parent ROADMAP row is correct *for the
union of all four*. This plan does NOT collapse that estimate — it
breaks the work into bite-sized pieces so each capability can be
activated independently as user demand surfaces.

## Pre-flight: binding probe extension

Before any of the four capabilities are committable, the existing
`NURBS_BOOLEAN_BINDINGS` probe in `src/lib/occtWorker.js` must be
extended to cover the new OCCT classes each capability needs. The
probe is a one-shot diagnostic at `loadOcct()` boot; adding entries
costs ~5 LOC and `console.info` lines.

Proposed extension (single shared task across all four capabilities) —
append the classes below to `NURBS_BOOLEAN_BINDINGS` (or a sibling
`NURBS_PHASE_4_FULL_BINDINGS` array) in `src/lib/occtWorker.js`:

- **Capability 1** — `BOPAlgo_Builder` (does it expose
  `SetFuzzyValue`?), `BRepAlgoAPI_Section`, `ShapeFix_Shape`,
  `ShapeFix_Solid`, `ShapeUpgrade_UnifySameDomain`.
- **Capability 2** — `BRepFeat_SplitShape`, `BRepProj_Projection`,
  `BRepBuilderAPI_MakeFace_18` (or whichever overload accepts
  surface + wire).
- **Capability 3** — `GeomAPI_ExtremaCurveSurface`, `GeomFill_NSections`,
  `ShapeAnalysis_Surface`, `Geom_BSplineSurface.SetPole_1`/`_2`.
- **Capability 4** — `BRepLProp_SLProps` / `GeomLProp_SLProps` (curvature
  comb). `GeomAbs_Shape` enum already probed implicitly via `blend_srf`
  — confirm `GeomAbs_G3` is *not* present (the structural impossibility
  in C++ should also be a structural impossibility in the binding).

Probe outcome is the input to every "Capability N — verification task"
below. Until we run the probe on the current build and post output to a
ROADMAP child row, every estimate in this plan reads as conditional on a
`MISSING` bucket of zero.

**Task PB-1 — Extend binding probe** (~0.5 sonnet-day, blocking the rest):

- Append the classes above to `NURBS_BOOLEAN_BINDINGS` (or a sibling
  array) in `src/lib/occtWorker.js`.
- Log on boot via the existing `_logNurbsBooleanBindings` helper.
- No fallback logic yet — the probe just reports presence/absence.
- Post outcome to a child ROADMAP row so each capability's owner knows
  which fallback paths to design for.

---

## Capability 1: Robust NURBS-NURBS booleans

### What it is

A `surface_boolean` (or equivalently, a `kind` parameter on an extended
`feature_boolean`) that accepts two `TopoDS_Face` / `TopoDS_Shell`
operands — not solids — and returns the intersection / difference /
union of the underlying NURBS surfaces as trimmed-face fragments. This
is the case the v1 plan deliberately routes around via
`feature_to_solid`; the v1 plan's hint "run feature_to_solid on … first"
becomes unnecessary once this ships.

The intended user gesture is "cut this blend surface with that swept
surface" — both Class-A surface inputs, no implied solid round-trip,
no sewing tolerance to tune at the cap-faces step.

### Why now (user signals, current pain)

- **Surface-only workflows are the jewelry-CAD norm.** Designers build
  ring shanks as a stack of surface patches, blend them, then trim to
  silhouette. Forcing them through `feature_to_solid` mid-tree
  introduces a tolerance step at every surfacing breakpoint.
- **The v1 cap-then-cut path's tolerance budget is fragile.** Once T7
  (integration test) runs on real NURBS shanks, expect the "BOPAlgo
  failed on sewn-from-NURBS solid" failure mode flagged in the v1 plan's
  "Highest-risk open question" section. Surface-direct booleans avoid
  the tolerance compounding by skipping the solid stage entirely.
- **LLM authoring signal.** Once `surface_continuity` is in regular use,
  expect the model to start emitting `cut(blend, sweep)` shaped nodes
  via `write_file` — this is the doc-search-tool-consolidation pattern
  the LLM landed on for sketch ops.

### OCCT support assessment

**`BRepAlgoAPI_*` Cut/Fuse/Common don't strictly require solids** —
they wrap `BOPAlgo_Builder`, which accepts any `TopoDS_Shape`. The
caveat: with face operands the result is a `TopoDS_Compound` of trimmed
fragments, sometimes with dangling edges where one surface terminates
mid-face on the other. `breptToMesh` already walks compounds so display
should work unchanged.

**Known failure modes on non-solid operands:**

1. Empty result on non-intersecting surfaces — surface as `OP_FAILED`.
2. Tangential intersections → zero-length section edges from
   `BRepAlgoAPI_Section`; fragile under `Cut`.
3. Self-intersecting section curves on pathological NURBS pairs — OCCT
   aborts. Mitigation: `BOPAlgo_Builder.SetFuzzyValue(eps)` —
   **binding unverified** (scoping doc flagged "Likely missing").
4. If `SetFuzzyValue` is missing, fallback is `ShapeFix_Shape` pre-pass
   at default tolerance, OR custom WASM rebuild.

**Binding coverage:** `BRepAlgoAPI_Cut_3` is confirmed (used in
`occtWorker.js`). `BRepAlgoAPI_Section`, `BOPAlgo_Builder`,
`SetFuzzyValue`, `ShapeFix_Shape`, `ShapeUpgrade_UnifySameDomain` are
**all unknown** — verification via PB-1 probe required.

**Honest uncertainty:** I don't know whether `SetFuzzyValue` is callable
on the binding even if `BOPAlgo_Builder` is bound. opencascade.js's
binding generator often whitelists classes but trims method overloads.
Only a runtime call resolves.

### Design sketch

**Op kind name:** `surface_boolean`. Distinct from `boolean` (which the
v1 plan introduces for solid-on-solid) so the inspector affordances and
error envelopes don't have to overlap. Both ops survive long-term:
`boolean` is the cheap path; `surface_boolean` is the precise path.

**Worker dispatch:** new `case 'surface_boolean'` in both evaluator
switches (template: v1 plan's `boolean` dispatch — finalize prev mesh,
don't cleanup current since opSurfaceBoolean may reference it via
target ids, clear `currentFaceNamer`).

`opSurfaceBoolean(oc, prev, node, sketches, tracker, bodyMap)`:
- Resolve `node.target_a_id` + `node.target_b_id` via `bodyMap` (same
  plumbing the v1 plan introduces for `feature_boolean`).
- Skip the solid topology check — accepts Face/Shell.
- Optional `ShapeFix_Shape` pre-pass on each operand (probe-gated).
- Dispatch `BRepAlgoAPI_Cut_3` / `Fuse_3` / `Common_3` with
  `SetFuzzyValue(node.fuzziness || 1e-4)` if the binding exists.
- Optional `ShapeUpgrade_UnifySameDomain` cleanup (probe-gated).
- Return the `TopoDS_Compound` result; downstream ops + `breptToMesh`
  handle it natively.

**Python tool surface:** `feature_surface_boolean` in `surfacing.py`.
Fields: `file_id`, `target_a_id`, `target_b_id`, `kind` (cut/fuse/common),
`fuzziness` (number, default 1e-4 — raise to 1e-3 if tangent intersection
fragments go missing). Registered in `_TOOL_MODULES` in
`kerf_cad_core/plugin.py`.

**Inspector affordances:**

- Category: **Surfacing** (same as sweep / blend / network), not
  **Modify** — keeps the mental model "this is still a surfacing
  op, just with two inputs".
- Fields: `target_a_id` (feature_picker), `target_b_id` (feature_picker),
  `kind` (select cut/fuse/common), `fuzziness` (number, default 1e-4).
- New affordance vs v1's `boolean`: a "Preview intersection" toggle that
  renders the `BRepAlgoAPI_Section` curve as a wireframe overlay,
  without committing the boolean. Defers to a Phase 4-after-this row.

### Tasks

| Task | File paths | Estimate (sonnet-days) |
|---|---|---|
| **C1-T1** Probe extension verification | run worker boot, capture binding outcome, post to ROADMAP. Inputs: PB-1 outcome. | 0.5 |
| **C1-T2** `opSurfaceBoolean` worker handler | `src/lib/occtWorker.js` (new function) + both evaluator switch wirings | 1.5 |
| **C1-T3** `feature_surface_boolean` Python tool | `packages/kerf-cad-core/src/kerf_cad_core/surfacing.py` (new spec + handler) + `_TOOL_MODULES` registration in `plugin.py` | 0.5 |
| **C1-T4** LLM doc page | `packages/kerf-chat/llm_docs/feature_surface_boolean.md` (new file, template `feature_sweep1.md`) | 0.5 |
| **C1-T5** Inspector entry | `src/components/FeatureView.jsx` — append to `FEATURE_KINDS` + `FEATURE_CATEGORIES.surface` | 0.5 |
| **C1-T6** Pytest schema + error coverage | `packages/kerf-cad-core/tests/test_feature_surface_boolean.py` (12 cases, no DB) | 0.5 |
| **C1-T7** Vitest worker dispatch + inspector | `src/__tests__/featureSurfaceBoolean.test.js` (8 cases) | 0.5 |
| **C1-T8** WASM integration test | `src/__tests__/surfaceBooleanIntegration.test.js` — gated by `occtRunner.test.js` skip pattern; three end-to-end scenarios (blend ∩ sweep, network − blend, sweep ∪ blend) | 1.0 |
| **C1-T9** Fallback path: `SetFuzzyValue` missing | if C1-T1 probe shows missing, add `ShapeFix_Shape` pre-pass at default tolerance; document degraded robustness budget in doc page | 1.0 |
| **C1-T10** Fallback path: `BOPAlgo_Builder` missing | if `Cut_3` / `Fuse_3` / `Common_3` reject non-solid operands at runtime (the binding shape may enforce solid-typed args), the fallback is a custom WASM rebuild — escalate, don't implement | n/a (escalation) |

**Total: ~6.5 sonnet-days assuming bindings cooperate. +2 days if
`SetFuzzyValue` fallback path is needed. Indeterminate if C1-T10
escalation triggers.**

### Risks + open questions

- **Q1.** Does `BRepAlgoAPI_Cut_3` actually accept Face/Shell-typed
  arguments in opencascade.js 1.1.x? The C++ API takes `TopoDS_Shape`
  (a base class) so it should — but TS/JS-level type narrowing in the
  binding generator might enforce `TopoDS_Solid`. **Honest answer: I
  don't know without trying it.** Resolution: C1-T1 + a follow-up
  runtime call test.
- **Q2.** Does the `breptToMesh` path tessellate `TopoDS_Compound`s
  cleanly, or do face fragments disappear at the explode step? Static
  search shows compounds are walked by `TopExp_Explorer` (occtBridge.js
  has multiple uses) — should work but unverified for compound-of-faces.
- **Q3.** When `Common_3` is missing and v1 falls back to the
  `A − (A − B)` identity, does that identity hold on face-fragment
  outputs the same way it does on solids? **I don't know.** The
  identity assumes both sides have well-defined topology under the
  cut operator; face fragments might produce a different fragment count
  on the inner vs outer cut. C1-T9 should test this explicitly.

### Done criteria

- C1-T1 binding-coverage report posted to ROADMAP.
- Three end-to-end integration scenarios pass on the real WASM build
  (gated like `occtRunner.test.js`).
- `feature_surface_boolean` documented in `llm_docs/` and reachable from
  the chat agent (verified via a manual chat session).
- Inspector affordance present in `FeatureView.jsx`.
- Schema pytest + dispatch vitest green.

---

## Capability 2: Trim-by-curve

**Status (2026-05-16):** pure-Python geometry layer + worker wiring shipped.
  Remaining: C2-T1 WASM binding probe, C2-T7 LLM doc page, C2-T8 inspector
  entry, C2-T10 Vitest dispatch, C2-T11 WASM integration test, C2-T12 fallback
  (if BRepFeat_SplitShape absent).

### What it is

Given a face and a 3D curve (sourced from a sketch or from another
feature's edge), split the face along the curve's projection onto the
face's surface, then keep one side. The Rhino verb is "Trim" /
"Split". The kerf op is `feature_trim_face`.

Concrete use cases: cut a stone-setting window into a NURBS ring
shoulder; remove a teardrop region from a blend surface before sewing;
notch a sweep at a sketch curve.

### Why now (user signals, current pain)

- No current path to remove a sub-region of a NURBS face. The only
  workaround is `feature_to_solid` then `pocket` — which loses surface
  identity and forces tolerance compounding.
- Jewelry users repeatedly hit the "I want a window in this surface"
  request; currently they're routed to JSCAD's mesh `subtract` which is
  lossy.

### OCCT support assessment

**Primary class: `BRepFeat_SplitShape`** —
`SplitShape(face); Add(wire, face); Build(); Left()/Right()/DirectLeft()`
returns the halves. Input wire must lie on the face — workflow:
3D curve → `BRepProj_Projection` onto face surface (produces a wire
with 2D pcurves) → feed both to `SplitShape.Add()`.

**Known failure modes:** curve not fully crossing face boundary (need
closed loop or boundary-terminating endpoints), C1 discontinuities on
projected wire (mitigation: `ShapeFix_Wire` pre-pass), pcurve tolerance
mismatch (re-project at coarser tolerance), empty projection (cutter
misses face → `OP_FAILED`).

**Binding coverage:** `BRepFeat_SplitShape`, `BRepProj_Projection`,
`ShapeFix_Wire`, `BRepBuilderAPI_FindPlane`, `BRepBuilderAPI_MakeFace_18`
**all unknown**. `BRepFeat_SplitShape` is the riskiest binding in this
entire plan — niche feat-class that the opencascade.js whitelist may not
cover. **Verification: PB-1 probe.** If missing, fallback is to roll
trim-by-curve via `BRepAlgoAPI_Section` + auxiliary extruded prism
(uglier, but uses already-bound classes).

### Design sketch

**Op kind name:** `trim_face`. Single face input + single curve input +
side selector.

**Worker dispatch:** new `case 'trim_face'` (in-place; clear
`currentFaceNamer` since trim invalidates positional face IDs).

`opTrimFace(oc, prev, node, sketches, tracker)`:
- Resolve `node.target_face_id` from `prev` (existing `faceById`).
- Resolve cutter: `cutter_sketch_path` → 3D wire via `wireForSketchPath`,
  OR `cutter_edge_ref` → edge from referenced body.
- Project wire onto face surface via `BRepProj_Projection` +
  `ShapeFix_Wire` cleanup.
- `BRepFeat_SplitShape(face)` + `.Add(projectedWire, face)` + `.Build()`.
- Pick side per `keep_side` heuristic.
- Rebuild parent shape with split face swapped in (template:
  `opPocket`'s body-rebuild step).

**Python tool surface:** `feature_trim_face` in `surfacing.py`. Required:
`file_id`, `target_id`, `target_face_id`. One of `cutter_sketch_path`
(absolute .sketch path) or `cutter_edge_ref` (`{feature_id, edge_id}`)
must be present — validated in the runtime handler. Optional
`keep_side ∈ {larger, smaller, sketch_inside, sketch_outside}` (default
`sketch_inside` when cutter is a closed loop; `larger` otherwise).

**Inspector affordances:**

- Category: **Surfacing** (the face is part of a surface body) or
  **Modify** (the op modifies an existing body). I lean **Surfacing**
  for discoverability — the user reaches for "Trim" while looking at a
  surface tile.
- Fields: `target_id` (feature_picker), `target_face_id` (face_picker_single),
  `cutter_sketch_path` (sketch_picker), `keep_side` (select).
- The `cutter_edge_ref` variant is initially CLI-only (LLM
  authoring); inspector exposes only the sketch path.

### Tasks

| Task | File paths | Estimate (sonnet-days) |
|---|---|---|
| **C2-T1** Probe extension verification for SplitShape + BRepProj | confirm at boot; if missing, design fallback via `BRepAlgoAPI_Section` + auxiliary prism | 0.5 |
| **C2-T2** Helper: `projectCurveToFace(oc, wire, face, tracker)` in `src/lib/occtBridge.js` | wraps `BRepProj_Projection` + `ShapeFix_Wire` cleanup | 1.0 |
| **C2-T3** `opTrimFace` worker handler | `src/lib/occtWorker.js` (new function, ~120 LOC) + both evaluator switches | 1.5 |
| **C2-T4** Side-selection heuristic | "larger" / "smaller" via face area; "sketch_inside" / "outside" via point-in-wire test on a representative parameter — same logic as `pocket` boundary classification | 1.0 |
| **C2-T5** Face-replacement-in-parent-shape | rebuild parent solid/shell with split face swapped in — `BRepBuilderAPI_MakeShape` + walk pattern (template: `opPocket`'s body-rebuild step) | 1.5 |
| **C2-T6** `feature_trim_face` Python tool | `surfacing.py` + `_TOOL_MODULES` | 0.5 |
| **C2-T7** LLM doc page | `packages/kerf-chat/llm_docs/feature_trim_face.md` | 0.5 |
| **C2-T8** Inspector entry | `src/components/FeatureView.jsx` | 0.5 |
| **C2-T9** Pytest schema | `packages/kerf-cad-core/tests/test_feature_trim_face.py` | 0.5 |
| **C2-T10** Vitest dispatch | `src/__tests__/featureTrimFace.test.js` | 0.5 |
| **C2-T11** WASM integration test (3 scenarios) | sketch cuts hole in blend face; edge-derived cutter on sweep face; degenerate-cutter error path | 1.5 |
| **C2-T12** Fallback path (if C2-T1 negative) | `BRepAlgoAPI_Section` + auxiliary prism approach — significantly more code, separate task to keep scope clear | 3.0 |

**Total: ~9.5 sonnet-days happy path. +3 days for fallback. Higher
than the v1 plan because of the face-replacement step (C2-T5) — that
is genuinely tricky on multi-face solids.**

### Risks + open questions

- **Q1.** Does `BRepFeat_SplitShape` exist in opencascade.js 1.1.x?
  Static search shows zero references in `src/`. The class is in OCCT
  core (not a community module) so it *should* be on the standard
  whitelist — but feat-classes are sometimes trimmed for binary-size
  reasons. **I don't know.** C2-T1 resolves.
- **Q2.** Does the side-selection heuristic match user intent across
  jewelry / mech / arch use cases? "sketch_inside" assumes the cutter is
  a closed loop; "larger/smaller" is ambiguous for near-equal splits. We
  may need a UI-driven "pick a region" mode (face_picker on the
  intermediate split result).
- **Q3.** How does trim-by-curve interact with persistent face naming?
  The trim splits one face into two; the v1 face-naming scheme assigns
  positional `face-N` IDs, so any downstream op referencing the trimmed
  face is broken on re-evaluation. **Defer:** depends on Phase 4 CAD
  persistent-naming row landing. Cross-link in C2-T7 doc page.

### Done criteria

- C2-T1 binding outcome posted.
- Three integration scenarios pass on real WASM.
- Inspector affordance functional; manual chat session demonstrates the
  jewelry use case (sketch in face → cut hole).
- Schema + dispatch tests green.

---

## Capability 3: matchSrf

### What it is

Adjust the boundary of `surface_A` so its edge tangent (G1) or
curvature (G2) matches the corresponding edge of `surface_B`. The Rhino
verb is "MatchSrf". Workflow: build a sweep, build a blend, find the
seam looks broken at G1; run matchSrf with the sweep as target and
blend as reference; the blend's control points near the seam adjust to
get a clean continuity match.

This is **the** Class-A surfacing tool — automotive / consumer-product
ID work depends on it. Jewelry uses it less heavily but the "match the
shank top to the bezel base" case is a real demand source.

### Why now (user signals, current pain)

- `surface_continuity` (shipped) **queries / sets the requested
  continuity** on a node, but doesn't enforce it post-hoc on existing
  geometry. If `blend_srf` was built with continuity G1 but the
  upstream `sweep1` later moves slightly, the blend's edge tangents
  drift. matchSrf is the post-hoc fix.
- Without matchSrf the user's only recourse is to delete and rebuild
  the blend with adjusted inputs, hoping the OCCT solver converges to
  a matching tangent — which it usually doesn't on real shapes.

### OCCT support assessment

**This is where the plan gets honest.** OCCT does not expose a single
"match surface edge" API. Three candidate approaches:

- **Approach 1: `BRepFill_Filling` with continuity constraint** (same
  class `blend_srf` uses for fresh builds). Add target + reference
  edges as constraints, set `GeomAbs_Shape` on the reference. Solver
  re-builds target's near-seam region. **Pro:** binding confirmed.
  **Con:** rebuilds the *entire* face, destructive for large faces
  with complex interiors.
- **Approach 2: control-point adjustment via
  `Geom_BSplineSurface.SetPole`.** Walk the near-seam pole row, adjust
  to satisfy tangent / curvature constraints, leave interior poles
  alone. **Pro:** surgical. **Con:** binding unverified; requires
  hand-rolled 3-4×3-4 linear solver on the worker side.
- **Approach 3: `GeomFill_NSections` blend.** Multi-section sweep
  with one section per edge. **Pro:** more elegant than Approach 2.
  **Con:** binding unverified; produces a *new* transition strip
  rather than modifying surface_A in place.

**Honest assessment.** I don't know which approach the binding coverage
supports. C3-T1 probes `GeomFill_NSections`, `GeomAPI_ExtremaCurveSurface`,
`ShapeAnalysis_Surface`, `Geom_BSplineSurface.SetPole_N`,
`BRepFill_Filling.SetConstrParam`. Worst case (all three fail):
escalate to custom WASM rebuild OR defer with clear "blocked on"
notation.

**G1 / G2 enforcement asymmetry caveat.** Even with G1 honoured, G2
may silently degrade — `blend_srf` already hits this (its `cont ===
'G2'` branch uses `GA.GeomAbs_G2 ?? 2`; the enum value `2` is standard
but the *binding* may not honour curvature continuity). matchSrf
inherits the asymmetry.

### Design sketch

**Op kind name:** `match_srf`.

The op shape depends on which approach C3-T1 enables. **Best case
(Approach 1):** `opMatchSrf` resolves target + reference faces via
`faceById` on bodyMap-resolved bodies, resolves edges via `edgeById`,
builds a `BRepFill_Filling` with both edges as constraints (target
edge free, reference edge carries the `GeomAbs_Shape` continuity),
then replaces the target face in its parent shape with the filling
result. The op takes a body pair (not just a face pair) because the
face needs to be re-stitched into the parent shape after rebuild.

**Python tool surface:** `feature_match_srf` in `surfacing.py`. All
required: `file_id`, target (`target_id` / `target_face_id` /
`target_edge_id`), reference (`reference_id` / `reference_face_id` /
`reference_edge_id`), `continuity ∈ {G0, G1, G2}`. G1 / G2 honour is
build-dependent — doc page surfaces this caveat prominently.

**Inspector affordances:**

- Category: **Surfacing**.
- Fields: target body / face / edge (cascaded pickers), reference body /
  face / edge (cascaded pickers), continuity (select G0/G1/G2).
- This is a face-pair picker pattern not present in the codebase today
  — see "Cross-cutting concerns" below.

### Tasks

| Task | File paths | Estimate (sonnet-days) |
|---|---|---|
| **C3-T1** Probe extension verification (approaches 1/2/3) | extend probe; run boot; document which approach is viable | 1.0 |
| **C3-T2** Approach selection + design pivot | based on C3-T1 outcome, pick one approach and update this plan's design sketch section | 0.5 |
| **C3-T3** `opMatchSrf` worker handler | `src/lib/occtWorker.js` (~150 LOC if Approach 1; ~250 if Approach 2; varies if Approach 3) | 2.5 |
| **C3-T4** Face-replacement-in-parent-shape | shared with C2-T5 — pull into a helper in `occtBridge.js` first | 0.0 (overlaps with C2) |
| **C3-T5** `feature_match_srf` Python tool | `surfacing.py` | 0.5 |
| **C3-T6** LLM doc page | `feature_match_srf.md`. Document the G1/G2 build-dependent honour caveat prominently | 0.5 |
| **C3-T7** Cascaded face-pair picker UI | `src/components/FeatureView.jsx` — new `face_pair_picker` kind that drives target face selection, then reference face selection, then per-face edge picker | 2.0 |
| **C3-T8** Pytest schema | `tests/test_feature_match_srf.py` | 0.5 |
| **C3-T9** Vitest dispatch + inspector | `src/__tests__/featureMatchSrf.test.js` | 0.5 |
| **C3-T10** WASM integration (G0/G1/G2 visual continuity assertion) | three scenarios + continuity-comb wireframe assertion | 2.0 |
| **C3-T11** Fallback path if all approaches negative | document blocked state; escalate to custom WASM rebuild or defer-with-reason | n/a (escalation) |

**Total: ~9.5 sonnet-days assuming any approach is viable. The
face-pair picker (C3-T7) is the surprise — it's a non-trivial UI build,
shared with C2-T8 partially but not fully.**

### Risks + open questions

- **Q1.** Of approaches 1/2/3, which is bound? **I genuinely don't
  know.** This is the most-honest "I don't know" in this plan.
  Resolution: C3-T1 + a one-page write-up posted to a ROADMAP child
  row.
- **Q2.** Even with G1 enforcement via `BRepFill_Filling`, does the
  rebuilt face *visibly* match the reference at the seam in the
  rendered mesh? Tessellation tolerance might hide a discontinuity that
  would re-emerge in downstream booleans. **I don't know.** C3-T10
  needs a curvature-comb-style visual assertion.
- **Q3.** Does Approach 2's pole-adjustment math (the only fully-
  surgical option) require numerical infrastructure (small linear
  solver) that we don't have on the worker side? If yes, the implementation
  cost spikes — we'd need to either pull in a tiny linear-algebra lib
  or hand-roll a 4x4 solver. Probably a 1-day hand-roll if we go this
  route.

### Done criteria

- C3-T1 probe outcome + approach selection posted.
- One integration scenario passes G1 visually (curvature-comb wire
  overlay shows tangent alignment).
- Inspector affordance functional; manual session demonstrates the
  jewelry "match shank top to bezel base" use case.
- Doc page is honest about G1-honoured-vs-G2-degraded by build.

---

## Capability 4: G3 continuity

### What it is

Extend `surface_continuity` from {C0/C1/C2, G0/G1/G2} to {…, G3}.
G3 means the surface's curvature *derivative* (the rate-of-change of
curvature) matches across the seam — a stricter constraint than G2.
Required for Class-A automotive surfaces; jewelry-CAD users almost
never need it, but having it on the menu is a Rhino-parity bullet.

### Why now (user signals, current pain)

- Honest answer: there is no current user demand for G3 surfacing.
- The reason it's in this plan: ROADMAP's `surface_continuity`
  documentation already implicitly invites the question by enumerating
  G0/G1/G2 — leaving G3 out is a visible gap to a Rhino user reading
  the docs.
- Most-likely use case is a single design partner doing automotive ID
  work; if no such partner shows up, this capability stays a
  documentation-only stub.

### OCCT support assessment

**Hard research question. Does OCCT expose G3 anywhere?**

The `GeomAbs_Shape` enum in standard OCCT has values:
- `GeomAbs_C0` = 0
- `GeomAbs_G1` = 1
- `GeomAbs_C1` = 2
- `GeomAbs_G2` = 3
- `GeomAbs_C2` = 4
- `GeomAbs_C3` = 5
- `GeomAbs_CN` = 6

No `GeomAbs_G3`. Parametric C3 exists; geometric G3 does not.

**This means:** OCCT's `BRepFill_Filling.Add(edge, GeomAbs_Shape, true)`
cannot be called with a G3 constraint — the enum literally doesn't
exist. The only paths forward are:

1. **Approximate G3 via dense C2 + visual curvature combs.** Build the
   surface with the highest available continuity (C2 / G2), then expose
   a curvature-comb inspector that visually flags G3 mismatches the
   user can manually adjust. **This is the recommended path** — it's
   honest, ships value (the comb is useful at G2 too), and avoids the
   custom-WASM-build rathole.
2. **Custom WASM build adding a G3 approximation in C++.** Implement
   `BRepFill_FillingG3` in a Kerf-specific fork of opencascade.js,
   threading a pole-adjustment pass after the standard G2 fill. Cost:
   1-2 weeks of C++ + WASM toolchain work per maintainer; ongoing
   maintenance every OCCT version.
3. **Defer indefinitely with a clear "blocked on OCCT upstream"
   notation** until a paying user requests it.

### Design sketch

**Recommended path (option 1):** ship as a documentation + inspector-
visualisation feature, not a new op.

- Add a "Curvature comb" toggle to the `surface_continuity` inspector
  affordance (where `set_continuity` already lives) — when enabled,
  render hair-like normal vectors along each edge, scaled by local
  curvature derivative. Visually obvious G3 mismatches show as kinks
  in the comb at the seam.
- Update `surface_continuity` to accept `G3` as a *query* value
  (returns "approximation only — OCCT lacks native G3 enforcement; use
  the curvature comb to inspect") but reject it as a *set* value with a
  clear error message.
- Documentation update: `surfacing.md` gains a "Why no G3 enforcement"
  section that explains OCCT's enum limitation. Honest framing.

**Alternative path (option 2):** if a design partner emerges, file a
separate plan doc for the custom WASM rebuild work. Out of scope for
this plan.

### Tasks (recommended path)

| Task | File paths | Estimate (sonnet-days) |
|---|---|---|
| **C4-T1** Curvature-comb computation | new helper `computeCurvatureComb(oc, edge, samples)` in `src/lib/occtBridge.js` — samples N points along edge, computes principal curvatures via `BRepLProp_SLProps` or `GeomLProp_SLProps`. Probe `BRepLProp_SLProps` first | 1.5 |
| **C4-T2** Comb rendering | new Three.js helper in `src/lib/renderHelpers.js` — renders the comb as line segments overlaid on the mesh; toggled by a viewport flag | 1.5 |
| **C4-T3** Inspector toggle in surface_continuity entry | `src/components/FeatureView.jsx` — "Show curvature comb" bool field that drives the renderer | 0.5 |
| **C4-T4** `surface_continuity` accepts G3 as query | Update `surfacing.py::surface_continuity` schema enum to add `G3`; if `set_continuity == "G3"` return descriptive `BAD_ARGS` error; if querying, return the comb-derived qualitative assessment | 0.5 |
| **C4-T5** Doc update | `packages/kerf-chat/llm_docs/surfacing.md` — new "G3 continuity (approximation only)" section; explain OCCT enum limitation; explain comb usage | 0.5 |
| **C4-T6** Vitest for comb math | `src/__tests__/curvatureComb.test.js` — 6 cases (planar edge → flat comb; cylindrical edge → uniform comb; bezier edge → varying comb) | 0.5 |
| **C4-T7** Pytest for surface_continuity G3 schema | extend `tests/test_surface_continuity.py` | 0.5 |

**Total: ~5.5 sonnet-days for the recommended path. The custom-WASM
alternative is 2+ weeks and out of scope here.**

### Risks + open questions

- **Q1.** Is `BRepLProp_SLProps` / `GeomLProp_SLProps` bound? Used by
  the existing 5-axis CAM work (per ROADMAP T1 line) — likely bound.
  C4-T1 verifies.
- **Q2.** Does the curvature-comb visualisation belong on the
  surface_continuity inspector or as a global viewport overlay?
  Argument for global: it's useful regardless of which node is
  selected. Argument for local: it ships with the relevant feature. I
  lean local for the first cut, with a "promote to global" follow-up
  PR if usage signals.
- **Q3.** **The biggest "I don't know":** is the recommended path
  (comb visualisation, no enforcement) acceptable as "shipping G3" for
  the user's Phase 4 completion criterion? It's a Rhino-parity gap if
  the user expects enforcement. Resolution: surface this question
  explicitly in the parent ROADMAP row before activating any of C4-T1
  through C4-T7. If the user wants enforcement, this capability
  becomes "blocked on custom WASM build" and the only honest answer is
  to defer.

### Done criteria

- Either: (a) curvature-comb shipped + doc honest about OCCT
  limitation, OR (b) explicit "blocked on OCCT upstream / custom
  build" notation posted to ROADMAP with the user's acknowledgement.

---

## Cross-cutting concerns

### Binding probe extension (PB-1)

The `NURBS_BOOLEAN_BINDINGS` array currently covers 3 classes; this
plan needs ~14 new entries (Capability 1: 4; Capability 2: 4;
Capability 3: 4; Capability 4: 2). The extension is one tiny PR.

The probe output should be promoted from `console.log` to a
structured `getNurbsPhase4Bindings()` export so test code can
assert capability gates. The current `getNurbsBooleanBindings` pattern
is exactly the template.

### Test infrastructure for surface-only ops

Most existing integration tests (`occtRunner.test.js` template) assume
the output is a solid that gets meshed and inspected. Surface-only
outputs (Capability 1's compound-of-faces; Capability 2's split-face;
Capability 3's rebuilt face) need adjusted assertions:

- Tessellation: confirm the result has > 0 mesh vertices.
- Face count: assert the expected number of faces in the
  compound/shell.
- For Capability 3 specifically: a curvature-continuity assertion —
  sample N points on each side of the seam, compare principal curvatures
  pairwise, expect `|diff| < tolerance` per the chosen G-level.

Recommend a shared `assertSurfaceTopology(shape, { expectedFaces,
expectedShells, expectMeshNonEmpty })` helper in
`src/__tests__/helpers/surface.js`.

### Inspector UX — face-pair picker

Capabilities 2 and 3 both need a richer face-selection UX than the
existing `face_picker_single`. Capability 3's `match_srf` specifically
needs "target face from body A, reference face from body B". The
existing pattern (one-at-a-time + the dropdown shows whatever's
selected) doesn't compose for face-pair selection.

Proposal (C3-T7): new `face_pair_picker` field kind that:
- Renders two slots side-by-side ("Target" / "Reference").
- Each slot has its own feature-picker (drives body) + face-picker
  (drives face within that body).
- Edge selection happens as a follow-on within each slot.

This is a meaningful UI investment (~2 sonnet-days). If we ship
Capability 2 first (single-face picker reused), this can stay deferred
until Capability 3 ramps up.

### Persistent-face-naming interactions

Capability 2 (trim_face) and Capability 3 (match_srf) both modify the
face topology of their parent body. The existing positional `face-N`
ID scheme means any downstream op referencing the modified face has
broken references after re-evaluation. This is *exactly* the problem
the [persistent-face-naming.md](./persistent-face-naming.md) plan
addresses.

**Sequencing implication:** Capabilities 2 and 3 should ideally land
*after* persistent-face-naming, so the trimmed/matched face inherits
a stable identifier from the parent's sketch-anchored naming. If we
ship them first, every trim_face/match_srf chain breaks on any
upstream sketch edit.

If we ship before persistent-naming: document the caveat clearly in
each op's LLM doc page (template: how `feature_cut_from_sketch.md`
already calls out the face-id stability gotcha).

---

## Sequencing

### Which capability ships first

**Recommendation: Capability 1 (Robust NURBS-NURBS booleans) first.**

Rationale:

1. **Highest immediate value.** Once the v1 solid-cap path lands, every
   tolerance failure in T7 integration testing is direct evidence for
   shipping Capability 1. The pain is empirical, not speculative.
2. **Lowest UI cost.** Reuses the v1 `feature_boolean` inspector
   pattern; only the `kind` mental model splits ("solid" vs
   "surface"). No new picker UX needed.
3. **Best probe coverage.** The classes Capability 1 needs
   (`BOPAlgo_Builder`, `BRepAlgoAPI_Section`, `ShapeFix_Shape`) are the
   most likely to be bound — they're standard infrastructure used by
   higher-level classes. Even if `SetFuzzyValue` is missing, the
   fallback (ShapeFix pre-pass) ships value.
4. **Doesn't depend on persistent-face-naming.** Output is a
   compound-of-faces — face naming is per-evaluation anyway.

**Recommendation: Capability 4 (G3) second, but only as the documented
"recommended path" (curvature comb).** Lowest risk, smallest scope,
ships visible Rhino-parity progress. No probe gates beyond
`BRepLProp_SLProps`.

**Recommendation: Capabilities 2 + 3 wait for persistent-face-naming.**
Building these on top of positional face IDs would produce a fragile
re-evaluation story. The cost of waiting is real (real Class-A users
want matchSrf), but the cost of building-and-rebuilding is worse.

### Inter-capability dependencies

- Capability 2 + 3 share the face-replacement-in-parent-shape helper
  (C2-T5 / C3-T4). Whichever ships first should pull this into
  `occtBridge.js`; the second should consume it.
- Capability 3's face-pair picker is built first there but useful for
  any future multi-face op (boolean preview, surface comparison tools).
- Capability 4's curvature comb (C4-T1/T2) is reusable across all
  capabilities for inspector-side visual continuity checks. If shipped
  first, it makes Capability 3's done-criteria visual assertion easier.

### Reasonable PR cadence

| Order | Capability | PR count | Calendar |
|---|---|---|---|
| 1 | PB-1 binding probe extension | 1 | 0.5 day |
| 2 | Capability 1 — Robust NURBS-NURBS booleans | 4-5 (probe verif, worker, python+doc, inspector+tests, integration) | 1-1.5 weeks |
| 3 | Capability 4 — G3 (curvature-comb path) | 2-3 (comb helper+render, inspector+doc, tests) | 0.5-1 week |
| 4 | (wait for persistent-face-naming) | — | external |
| 5 | Capability 2 — Trim-by-curve | 4-5 | 1.5-2 weeks |
| 6 | Capability 3 — matchSrf | 4-5 | 1.5-2 weeks |

## Estimate aggregate

| Capability | Sonnet-days (happy path) | Sonnet-days (with fallbacks) |
|---|---|---|
| PB-1 (probe extension) | 0.5 | 0.5 |
| Capability 1 | 6.5 | 8.5 |
| Capability 2 | 9.5 | 12.5 |
| Capability 3 | 9.5 | 9.5 (no documented fallback — escalates) |
| Capability 4 (recommended path) | 5.5 | 5.5 |
| Cross-cutting (test helpers, face-pair picker pulled out) | 2.0 | 2.0 |
| **Total** | **33.5 days** | **38.5 days** |

**Calendar conversion:**

- **Single agent, serial cadence (1.5 days/sonnet-day with overhead):**
  ~50-58 calendar days = **10-12 weeks**.
- **Two parallel agents, with persistent-face-naming as serial
  prerequisite for C2+C3:** Capability 1 + 4 in parallel (1.5 weeks),
  persistent-face-naming as external block (~1 week assuming the
  existing 5.5-day plan), then C2 + C3 in parallel (2.5 weeks). Total
  ~**5-6 weeks**.

The "multi-year" framing on the parent ROADMAP row should be revised
downward in light of this breakdown — **2-3 months** is the more
honest estimate for the four capabilities at a sustained-engineering
pace, **excluding the escalation paths** (custom WASM rebuild for
SetFuzzyValue, SplitShape, or G3-enforcement). Those remain
multi-month if they trigger.

## Out of scope (still deferred past Phase 4)

- **Subdivision surfaces (T-splines)** — separate model paradigm;
  already partially shipped via Catmull-Clark subd in
  `kerf-imports/tools/subd.py`. Full T-spline editing is its own
  plan.
- **Scan fitting (point cloud → NURBS)** — `GeomAPI_PointsToBSplineSurface`
  already used by topology-opt; full reverse-engineering workflow
  (region growing, feature detection, surface family inference) is
  multi-month and not on the Phase 4 critical path.
- **NURBS-NURBS robustness test corpus** — the "pathological 100+
  case" library that commercial kernels maintain. Add when a design
  partner signs on with budget.
- **`SetFuzzyValue` custom WASM rebuild** — kept as an escalation path
  in Capability 1, not as an in-scope task.
- **G3 enforcement via custom OCCT extension** — kept as a deferred
  branch in Capability 4, not as an in-scope task.
- **Face-pair picker promoted to a general selection-mode primitive** —
  designed for matchSrf use; if a second use case shows up (cross-body
  fillet, surface comparison) we promote, not before.

## Honesty register (uncertain claims in this plan)

Surfaced for the parent's review before any task is activated:

1. **Capability 1's `BRepAlgoAPI_Cut_3` may or may not accept Face /
   Shell operands at the binding level.** The C++ API does; the JS
   binding might enforce solid types via TS narrowing. C1-T1 resolves;
   if negative, Capability 1 reduces to a thin wrapper over the v1
   path with no surface-direct value-add.
2. **Capability 3's matchSrf has three candidate approaches and I
   don't know which is bound.** This is the single most-uncertain
   capability. The 9.5-day estimate assumes one of the three works; if
   none do, the only honest answer is escalation or deferral. C3-T1 is
   the gate.
3. **Capability 4's G3 enforcement is structurally impossible in
   stock OCCT.** Recommended path ships the visualization-only
   approximation. Whether that meets the user's "Phase 4 complete"
   bar is a product question, not an engineering one — explicit
   user-confirmation gate before activating C4-T1.
