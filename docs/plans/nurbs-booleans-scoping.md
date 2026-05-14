# NURBS booleans + trimming — honest scoping pass

**Status**: scoping doc (not a commitment). Last-touched: 2026-05-14.

## TL;DR

A small, tractable v1 path **does exist** and is worth bookmarking
as a "next" if/when a user actually needs it: expose a **sweep-to-solid
capping helper** + wire the existing `BRepAlgoAPI_Cut` / `Fuse` /
`Common` against the resulting solids. Two new LLM tools
(`feature_cap_surface` + `feature_boolean`). **~3 weeks of work** if
the opencascade.js build already exposes `BRepBuilderAPI_Sewing` /
`BRepBuilderAPI_MakeSolid` (most likely true on the 1.1.x build) —
otherwise add ~2 weeks for a bindings rebuild.

The genuinely multi-year framing applies to a **different scope**:
robust trim-by-arbitrary-curve on free-form surfaces, NURBS-NURBS
boolean with watertight tolerance handling, and `matchSrf` /
`G3`-continuity edge matching. That work stays deferred.

**Recommendation**: ship the small scope as a `📋 next` if and only if
a user requests it. Until then, sit on the doc — the multi-year claim
on the parent ROADMAP row is materially correct *for the work users
actually mean when they say "NURBS booleans"*, and chasing the smaller
scope speculatively would harm the bigger backlog.

---

## Current state (Phase 4a — shipped)

Three NURBS-tier surfacing ops live and are wired end-to-end:

| Op | Worker entry | OCCT class | LLM tool |
|---|---|---|---|
| `sweep1` | `opSweep1` in `src/lib/occtWorker.js:512` | `BRepOffsetAPI_MakePipeShell` (single spine) | none (handler-only; reachable via `write_file`) |
| `sweep2` | `opSweep2` in `src/lib/occtWorker.js:580` | `BRepOffsetAPI_MakePipeShell` + `SetMode_3` rail2 spine | `feature_sweep2` in `backend/internal/tools/surfacing_tools.go:133` |
| `network_srf` | `opNetworkSrf` in `src/lib/occtWorker.js:651` | `GeomFill_BSplineCurves` (4-curve patch) preferred; falls back to `BRepOffsetAPI_ThruSections` over U-curves with V-curves advisory | `feature_network_srf` in `surfacing_tools.go:241` |
| `blend_srf` | `opBlendSrf` in `src/lib/occtWorker.js:730` | `BRepFill_Filling` with two `TopoDS_Edge` constraints | `feature_blend_srf` in `surfacing_tools.go:341` |
| `loft` (NURBS smoothing) | `opLoft` in `src/lib/occtWorker.js:812` | `BRepOffsetAPI_ThruSections_1(isSolid, isRuled)` with `SetSmoothing(true)` for C1/C2 hint | (no dedicated LLM tool; reachable via `write_file`) |

**Continuity story** (not its own tool — a parameter on each op):

- `network_srf`: `continuity ∈ {C0, C1, C2}`, default C1 (parametric continuity)
- `blend_srf`: `continuity ∈ {G0, G1, G2}`, default G1 (geometric continuity)
- `loft`: `continuity ∈ {C0, C1, C2}`; mapped to `SetSmoothing(false|true)` because the binding's `ThruSections` doesn't expose `GeomAbs_Shape` selector

Visualisation uses the standard OCCT tessellation path (`BRepMesh_IncrementalMesh` → `breptToMesh`).

**Tests**: `backend/cmd/test/scenarios/feature_files.go:212–443` covers the three LLM tools (sweep2, network_srf, blend_srf) end-to-end; 89 assertions.

**What's NOT shipped — and is the topic of this doc**:

1. Trimming a NURBS surface by an arbitrary curve drawn on it.
2. Boolean operations BETWEEN two NURBS surface bodies (cut one swept shape with another).
3. NURBS-to-NURBS *solid* booleans (vs the mesh-level CSG that JSCAD already gives us).
4. `matchSrf` / `G3` continuity / advanced surface-to-surface continuity matching.

---

## Audit 1: what does OCCT actually offer?

Despite the "NURBS booleans are deep kernel work" reputation, OCCT's
public C++ API is rich here. The relevant classes:

### Booleans (all already work on `TopoDS_Solid` *regardless* of underlying surface type)

| Class | What it does | Status in occtWorker.js |
|---|---|---|
| `BRepAlgoAPI_Cut` | Subtract solid B from solid A | **already used** (`opPocket`, `opHole`, `opPushPull`) — `BRepAlgoAPI_Cut_3` overload, src/lib/occtWorker.js:217, 368, 463 |
| `BRepAlgoAPI_Fuse` | Union solid A and B | **already used** (`opPushPull` fuse branch) — src/lib/occtWorker.js:458 |
| `BRepAlgoAPI_Common` | Intersection of solid A and B | **not used today**, but the class follows the same constructor pattern as Cut/Fuse |
| `BRepAlgoAPI_Section` | Curve(s) where two faces meet — needed for trim-by-other-surface | not used today |

**Key fact**: these classes don't care whether the input shape has
NURBS faces or planar faces. They walk `TopoDS_Solid` topology. So if
a user has a `sweep2` body (a NURBS-faced solid produced by
`pipe.MakeSolid()` after a closed-profile sweep) and a `pad` body
(planar-faced solid), `BRepAlgoAPI_Cut(sweep2, pad)` is in principle a
one-line call.

The **practical** blockers are two:

- The user-facing model doesn't have an "X cut Y" gesture today (no
  `feature_boolean` op, no `feature_cut` LLM tool with two
  feature-id arguments). Boolean cuts happen as a *side effect* of
  `pocket` / `hole` / `push_pull`.
- Several of the NURBS ops produce `TopoDS_Face` (`blend_srf`,
  `network_srf` fallback) or `TopoDS_Shell` (open-profile `sweep1`),
  not `TopoDS_Solid`. They need a sewing / capping pass before they
  can participate in a solid boolean.

### Trimming a face by a curve

| Class | What it does | Status |
|---|---|---|
| `BRepFeat_SplitShape` | Split a face by a wire that lies on it; result is two faces sharing a new edge | not used today |
| `BRepBuilderAPI_MakeFace(surface, wire)` + the "add inner wire" form | Build a face from an arbitrary surface bounded by a wire (and optional hole wires) | partial — `BRepBuilderAPI_MakeFace_15(wire, onlyPlane=true)` is used in occtBridge.js:159 for **planar** face creation; the surface-input overload (`_18`?) isn't exercised |
| `Geom_TrimmedSurface` / `Geom2d_TrimmedCurve` | Bounded-parameter trim of an underlying B-spline surface; pure-geom, not topology | not used today |
| `ShapeUpgrade_UnifySameDomain` | Merge co-planar / co-surface faces after splits | not used today |

The clean path for "cut a hole in a freeform surface" is:

1. Project a wire (drawn or imported from a sketch) onto the target
   face, producing a wire that lies on its surface
   (`BRepProj_Projection` or `BRepAlgoAPI_Section` against a tool
   surface).
2. `BRepFeat_SplitShape.Add(wire, face)` → `Build()` → harvest the
   inside-the-wire face(s).
3. Remove them from the parent shell with `BRepAlgoAPI_Cut` (against a
   prism tool) or by direct topology surgery (`BRep_Builder.Remove`).

This is doable but not trivial — the projection step has tolerance
issues on twisty NURBS, and `SplitShape` is reportedly fragile when
the wire has C1 discontinuities or near-tangent intersections with the
face boundary.

### NURBS-NURBS solid boolean (the famously fragile case)

Internally, OCCT's `BOPAlgo_Builder` (which `BRepAlgoAPI_Cut` /
`Fuse` / `Common` dispatch to) does:

1. Section all face-face pairs (this is where it gets expensive — N×M
   surface-surface intersections, each producing parameter-space
   curves on both faces).
2. Build a shared graph of vertices / edges / faces with consistent
   tolerances.
3. Replay the requested boolean on the graph.

**Where the fragility lives**: step (1) on two C2-continuous NURBS
patches with shallow tangent intersections produces intersection
curves whose 3D ↔ 2D-parameter mapping has numerical drift. OCCT's
default linear tolerance (`Precision::Confusion()` = 1e-7) is often
too tight, and the user has to either pre-scale the model or call
`SetFuzzyValue(eps)` on the builder. Parasolid handles this with
adaptive tolerance internally; OCCT exposes the knob and assumes the
caller will tune. This is the part that makes NURBS-NURBS booleans
"famously fragile" — **the algorithm exists, it's the robustness
budget that's not free**.

For Kerf's actual jewelry / mech-CAD use cases, the most common shape
of NURBS-solid boolean is "cut a NURBS-walled ring shank with a
prismatic bezel pad" — that's a NURBS-vs-planar pairing, and OCCT
handles it well today. The full NURBS-vs-NURBS boolean is the case
where tuning starts to matter.

---

## Audit 2: opencascade.js binding coverage

The project pins `opencascade.js ^1.1.1` (package.json). That release
ships a **partial** binding — it covers the most-used B-rep modelling
classes but omits some helpers. Probing for available bindings is
already a defensive pattern in occtWorker.js (`typeof oc.X !==
'undefined'`).

**Confirmed available** (used in tree):

- `BRepAlgoAPI_Cut_3` (3-arg overload with `Message_ProgressRange`) ✅
- `BRepAlgoAPI_Fuse_3` ✅
- `BRepOffsetAPI_MakePipeShell` (with `SetMode_2` / `SetMode_3` / `SetMode_5` overloads) ✅
- `BRepOffsetAPI_ThruSections_1` ✅
- `BRepFill_Filling` ✅ (defensively probed — exists in 1.1.1)
- `GeomFill_BSplineCurves` ✅ (defensively probed)
- `BRepBuilderAPI_MakeFace_15` (planar overload) ✅
- `BRepFilletAPI_MakeFillet` / `MakeChamfer` ✅
- `BRepPrimAPI_MakePrism_1`, `MakeRevol_2` ✅
- `BRepOffsetAPI_MakeThickSolid` ✅
- `TopExp_Explorer_2`, `BRepTools.OuterWire` ✅

**Likely available but unverified** (these are standard 1.1.x — would need a runtime probe):

- `BRepAlgoAPI_Common_3` — for intersection; same constructor shape as Cut_3 / Fuse_3
- `BRepBuilderAPI_Sewing` — for stitching face/shell collections into a closed shell. **This is the v1 blocker for surface→solid promotion.**
- `BRepBuilderAPI_MakeSolid_1` / `_2` / `_3` — wrap a shell as a solid
- `BRepBuilderAPI_MakeFace_18` (or similar) — face from arbitrary surface + bounding wire
- `ShapeFix_Shape`, `ShapeFix_Shell`, `ShapeFix_Solid` — heal precision / orientation problems on freshly-sewn shells
- `BRepProj_Projection` — project a wire onto a face's surface
- `BRepFeat_SplitShape` — split a face by a wire

**Likely missing / partial**:

- `BOPAlgo_Builder.SetFuzzyValue` — the precision knob for fragile NURBS booleans. May be on the Cut/Fuse/Common API or only on the lower-level builder. Need to confirm — if it's missing this is one of the things rebuilding the OCCT WASM with a wider whitelist would fix.
- `ShapeUpgrade_UnifySameDomain` — face merging post-boolean cleanup. Useful but not strictly required for v1.
- `GeomAbs_Shape` enum with `GeomAbs_G3`+ values — for `matchSrf`-style continuity. Already handled via numeric fallback in occtWorker.js:771.

**Mitigation when bindings are missing**: opencascade.js 1.1.x is
buildable from source via `opencascade.js/build`. Adding a class to
the `whitelist.yml` and rebuilding is a one-day exercise *if* one
machine has the Emscripten toolchain set up. Mid-2024 there was talk
of moving to a 2.x line — worth a re-check before doing a custom
rebuild.

---

## Scope options A–D

Per the brief, four candidate intermediate scopes:

### A. NURBS-solid booleans (NURBS body cut by / fused with a prismatic body)

**What it is**: expose `BRepAlgoAPI_Cut` / `Fuse` / `Common` as a
top-level `feature_boolean` op that takes two feature-tree node ids
and a kind (`cut` / `fuse` / `intersect`). Works today for any pair
where both sides reach `TopoDS_Solid`.

**Why it's the smallest viable scope**:
- Zero new OCCT bindings needed (Cut/Fuse already used inside `opPocket` / `opPushPull`)
- One new worker op, one new LLM tool, one new doc page
- Existing tests for pad+pocket already exercise the Cut path; this just promotes it to a user-facing tool

**What it doesn't solve**: surface bodies produced by `blend_srf`
(returns a `TopoDS_Face`) or open-profile `sweep1` (returns
`TopoDS_Shell`) can't participate. They need scope **A′** first
(below). For a *closed-profile* `sweep1` / `sweep2`, `pipe.MakeSolid()`
already produces a solid → A works out of the box.

**Concrete tasks**:
1. Add `opBoolean(oc, prev, node, sketches, tracker)` to occtWorker.js — wraps Cut/Fuse/Common dispatch by `node.kind`
2. Wire `case 'boolean'` into both timeline-evaluator switches (`evaluate` and `evaluateToFinalShape`)
3. Look up `node.target_id` + `node.tool_id` in already-evaluated bodies (similar to how `blend_srf` already looks up edges on prev — we'd extend the lookup to a body map across the timeline)
4. Add `feature_boolean` LLM tool in surfacing_tools.go (or a new boolean_tools.go)
5. Update `feature.md` LLM doc page to list the op
6. Add a `feature_files.go` scenario with at least three assertions

**Effort**: ~3 days (one engineer).

### A′. Sweep-to-solid capping helper (prerequisite for A on open-profile sweeps)

**What it is**: a wrapper that takes an open `TopoDS_Shell` (the
output of an open-profile `sweep1` or a stitched `blend_srf` + body
sides) and:
1. Identifies its boundary wires
2. Caps each with `BRepBuilderAPI_MakeFace`
3. Sews everything with `BRepBuilderAPI_Sewing`
4. Promotes to a `TopoDS_Solid` via `BRepBuilderAPI_MakeSolid`
5. (Optional) `ShapeFix_Solid` to heal tolerance / orientation

**Concrete tasks**:
1. Confirm `BRepBuilderAPI_Sewing` and `MakeSolid` are present on
   `opencascade.js@^1.1.1`. (Probe at worker startup; log presence in
   `import('opencascade.js')` resolver.)
2. New helper `surfaceToSolid(oc, shellOrFace, tracker)` in
   occtBridge.js (file lives next to `ringsToFace` which already does
   adjacent work)
3. New worker op `cap_surface` (or fold it into `feature_boolean` as
   an auto-promotion step when one side is a Face/Shell)
4. LLM tool `feature_cap_surface` with single-arg `target_id`

**Effort**: ~5 days, assuming the bindings probe comes back positive.
If `Sewing` / `MakeSolid` isn't bound, add ~2 weeks for an OCCT WASM
rebuild (which is its own self-contained yak-shave with a separate
risk profile — see the opencascade.js README on building from
source).

### B. Trim-by-curve on a single NURBS face

**What it is**: take a wire (from a sketch or projected onto a face)
and split a face by it, removing the inner piece. The "cut a hole in
a Class-A surface" gesture.

**Concrete tasks**:
1. Confirm `BRepFeat_SplitShape` is bound (uncertain — this class is
   less commonly used)
2. Confirm `BRepProj_Projection` is bound (likely is, used by
   `BRepFilletAPI_MakeFillet` internally)
3. Wire `face_id` selection (already in place via the FeatureView
   Faces pick mode) + sketch lookup
4. New worker op `face_split` / `trim_face`
5. LLM tool `feature_trim_face` with `target_id`, `face_id`,
   `cutter_sketch_path`
6. Tolerance / fragility budget — if the cutter wire has any C1
   discontinuities near the face boundary, `SplitShape` will fail or
   produce degenerate edges. This is the "famously fragile" half.

**Effort**: ~2 weeks. Significant unknowns around binding coverage
and robustness on real jewelry shapes. Would require a small test
corpus of "must-work" examples before claiming it ships.

**Risk**: highest of the four. The "robustness budget" is open-ended
on this one in a way that A / A′ aren't.

### C. NURBS-NURBS body boolean

**What it is**: the full case — two arbitrary NURBS-faced solids and
a robust boolean between them.

The algorithm exists in OCCT today (`BRepAlgoAPI_Cut` doesn't care
about face types) but the **robustness** story requires:

1. Fuzzy-value tuning (`BOPAlgo_Builder.SetFuzzyValue(eps)`) — and we
   don't know yet whether that's bound. Probably not.
2. A pre-pass `ShapeFix_Shape` on both operands to normalize
   tolerances.
3. Fallback paths when the section step produces zero curves (the
   bodies don't actually touch) or self-intersecting curves
   (degenerate cases).
4. A test corpus of pathological NURBS-NURBS cases — typically every
   commercial kernel maintains an internal one with hundreds of
   regressions.

**Effort**: 1–3 months if SetFuzzyValue is bound and the robustness
work pays off on a small corpus. 6+ months if the bindings need a
custom rebuild AND we need to maintain the corpus ourselves. This
**is** the "deep OCCT kernel work" the original ROADMAP framing
referred to — and the framing holds.

### D. Mesh-level booleans (frame as "the practical workflow today")

**What it is**: explicitly endorse the existing JSCAD `subtract` /
`union` / `intersect` mesh-CSG path for surface bodies. The user
imports the OCCT mesh output of `sweep2` into a `.jscad` file via the
existing assembly-level cross-kernel pattern, runs `subtract(jscad)`
on it, and accepts the kernel transition.

**Concrete tasks**:
1. Documentation only — add a section to `feature.md` and
   `assemblies.md` describing the workflow
2. Possibly a `feature_export_mesh` LLM tool that emits a
   per-feature mesh artifact a `.jscad` file can import (the cross-kernel
   bridge is already partially built for cross-project parts — same
   pattern)

**Effort**: ~2 days docs + ~3 days mesh-export helper. **Already mostly
works today** via the assembly-level mesh path; the work is making it
discoverable to users (and to the LLM) rather than building new
kernel code.

---

## Recommendation

### Pick: **A + A′ together** *as a `📋 next`* iff user demand surfaces

The smallest scope that delivers user-perceptible value is:

- **Step 1 (A′)**: cap surfaces into solids. Two new bindings to verify (Sewing, MakeSolid). One new helper in occtBridge.js.
- **Step 2 (A)**: expose Cut/Fuse/Common on solid-pairs as a `feature_boolean` op + LLM tool.

This is **~2 weeks of focused work** assuming bindings cooperate, **3
weeks** with a buffer for the bindings probe to fail and require a
hand-rolled MakeFace overload via existing primitives. Adds ~300 LOC
total across two files + one doc page + one test scenario.

User value: turns the existing `sweep2` / `blend_srf` / `network_srf`
ops from "produces a surface body you can look at" into "produces a
surface body you can subtract from a ring shank". This is the
delta most jewelry-CAD users would actually use.

### Defer: **B, C, matchSrf, G3 continuity, full robustness story**

B (trim-by-curve) and C (NURBS-NURBS boolean) both have unbounded
robustness budgets that don't pay off until the corpus problem is
solved. Defer until either:
- A specific user submits a repro case where A+A′ aren't enough, OR
- A jewelry/industrial-design design partner signs on with a willingness to fund the corpus work.

D is half-shipped already as the cross-kernel mesh path — it just
needs better discoverability copy. Could ride as a doc-only PR
alongside A+A′.

### Don't ship: **anything yet** — wait for demand

The honest scoping conclusion is: **the committable v1 exists** (A+A′
above) **but shouldn't be built speculatively**. The user base today
(jewelry-makers via Phase 4a, mechanical engineers via Phase 1–3)
hasn't asked for NURBS booleans; the multi-year framing on the
ROADMAP parent row is correct *for the work users mean*. Pre-building
A+A′ trades real engineering hours for a feature with no signal of
demand — better to keep the design doc on hand and ship the day a
user submits a feature request that includes a concrete repro.

Three signals would justify activating A+A′:
1. A user posts on the public issue tracker requesting "cut my swept ring with a planar bezel".
2. A jewelry-CAD design partner asks for it in a sales conversation.
3. The LLM's chat logs show it repeatedly trying to author `feature_boolean` nodes via `write_file` (i.e. the model is *asking* for the tool).

---

## Effort summary

| Scope | Bindings risk | Engineering | Robustness risk | User value (today) |
|---|---|---|---|---|
| A only | none (Cut/Fuse already used) | ~3 days | low | medium (works only for closed-profile sweep1/sweep2) |
| A + A′ | low (Sewing/MakeSolid likely bound; verify) | ~2–3 weeks | low–medium | **high** (works for all Phase 4a surfaces) |
| B | medium (SplitShape unverified) | ~2 weeks | **high** (curve-on-surface fragility) | medium-niche |
| C | high (SetFuzzyValue likely unbound) | 1–6 months | **very high** | high but unbounded scope |
| D | none | ~3 days doc + ~3 days helper | none | medium (mesh-level only; lossy STEP export) |

## Key OCCT classes / opencascade.js methods (load-bearing references)

For anyone activating the scope later, the load-bearing class names are:

- `BRepAlgoAPI_Cut_3`, `BRepAlgoAPI_Fuse_3` — **already used** in `occtWorker.js`. `BRepAlgoAPI_Common_3` would slot in identically.
- `BRepBuilderAPI_Sewing` — face-collection-to-shell. **Verify presence at runtime; this is the gating binding.**
- `BRepBuilderAPI_MakeSolid_1` / `_2` — shell-to-solid promotion.
- `BRepFeat_SplitShape` — for scope B (trim-by-curve).
- `BRepProj_Projection` — for scope B (wire-to-surface projection).
- `BOPAlgo_Builder.SetFuzzyValue` — for scope C (NURBS-NURBS robustness).
- `ShapeFix_Solid` / `ShapeFix_Shape` — for scope A′ / C (post-boolean healing).
- `ShapeUpgrade_UnifySameDomain` — for cleanup after splits.

The existing defensive `typeof oc.X !== 'undefined'` pattern in
`opBlendSrf` (occtWorker.js:755) is the right template for probing
these at op-entry.

## Recommended next action

**Wait for user demand.** When demand arrives, the 3-step plan is:

1. Add a one-shot binding-probe diagnostic to `occtWorker.js` boot
   that logs which of the eight classes above are present. Run it on
   the staging build to characterise the existing binding gap.
2. Implement A′ (capping helper) + A (`feature_boolean` op + LLM
   tool) on a branch.
3. Ship behind a hidden flag for a sprint, watch logs for tolerance
   failures, then flip to user-visible.

This doc gets linked from the ROADMAP NURBS Phase 4 row so the
decision trail is searchable; no ROADMAP commitment changes until
demand surfaces.
