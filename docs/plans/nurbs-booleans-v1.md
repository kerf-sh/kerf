# NURBS booleans v1 — implementation plan

**Status:** ACTIVATED. Supersedes the "wait for demand" recommendation in the
prior scoping pass.
**Owner:** TBD (sonnet agents per task).
**ROADMAP row:** *NURBS surfacing (Phase 4)* — flipped from "deferred" to
"🚧 in flight" with seven 📋 next sub-rows (T1–T7).

## Why now

User-demand signal received. The prior scoping doc
([`nurbs-booleans-scoping.md`](./nurbs-booleans-scoping.md)) had a clean
short-path for a small-scope v1 already mapped out — this doc is the
turn-the-crank version with sonnet-sized tasks, dependency graph, and per-op
schemas.

The scoping doc's three "activate the plan" signals (public-issue, design
partner, LLM repeatedly asking via `write_file`) have collapsed into one:
the user has explicitly green-lit the small-scope path. We are NOT taking
on the multi-year framing (full NURBS-NURBS robustness corpus, trim-by-
curve, `matchSrf`, G3 continuity) — that remains correctly deferred.

## Scope (carried over from scoping doc — DO NOT widen)

Two new ops, two new LLM tools, two new FeatureView inspector entries.

1. **`feature_to_solid` op (A′)** — promote a sewn-or-loose collection of
   faces / a shell to a `TopoDS_Solid`. Powered by `BRepBuilderAPI_Sewing` +
   `BRepBuilderAPI_MakeSolid_1`. Enables the surface-producing ops
   (`sweep1` open-profile, `blend_srf`, `network_srf` fallback) to feed
   into booleans.

2. **`feature_boolean` op (A)** — `{a, b, kind}` where `kind ∈ {cut, fuse,
   common}`. Wraps the already-used `BRepAlgoAPI_Cut_3` / `Fuse_3` plus the
   newly-needed `BRepAlgoAPI_Common_3`. Both operands must resolve to
   `TopoDS_Solid`; the op errors with a hint pointing at `feature_to_solid`
   if a Face/Shell shows up (no auto-promotion in v1 — kept explicit so
   tolerance failures surface at the promotion step, not buried inside the
   boolean).

Not in scope: trim-by-curve, NURBS-NURBS robustness tuning
(`SetFuzzyValue`), `matchSrf`, G3 continuity, mesh-CSG bridges. All
remain on the long-tail backlog where the original ROADMAP framing put
them.

## Binding-coverage audit findings

The two gating bindings live in `opencascade.js@^1.1.1` (pinned in
`package.json`). Confirmed-via-source-search status:

| Class | Status | Evidence |
|---|---|---|
| `BRepAlgoAPI_Cut_3` | ✅ in use | `src/lib/occtWorker.js:382, 519, 743, 781` |
| `BRepAlgoAPI_Fuse_3` | ✅ in use | `src/lib/occtWorker.js:776`, `src/lib/occtBridge.js:1023` |
| `BRepAlgoAPI_Common_3` | ❓ **unconfirmed** | not referenced anywhere in `src/`. Class follows the identical 3-arg `(shapeA, shapeB, Message_ProgressRange)` constructor shape as Cut/Fuse — overwhelmingly likely to be bound. **T1 runtime probe gates this.** |
| `BRepBuilderAPI_Sewing` | ❓ **unconfirmed** | not referenced anywhere in `src/`. The scoping doc flags this as the v1 blocker. **T1 runtime probe gates this.** |
| `BRepBuilderAPI_MakeSolid_1` | ❓ **unconfirmed** | not referenced anywhere in `src/`. Standard 1.1.x class — likely bound. **T1 runtime probe gates this.** |
| `BRepBuilderAPI_MakeShell` | ❓ **fallback candidate** | only used if T1 reveals `MakeSolid_1` is missing. Constructs an open `TopoDS_Shell` from a single face; a hand-rolled "promote shell to solid via direct topology" path can substitute via `BRep_Builder.MakeSolid` + `Add(solid, shell)`. |

**The probe (T1)** is a one-shot diagnostic in `loadOcct()` boot that logs
which of `{BRepAlgoAPI_Common_3, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid_1}`
are present using the existing `typeof oc.X !== 'undefined'` defensive
pattern (template: `opBlendSrf` in `src/lib/occtWorker.js:1062`). If any are
missing, T1 produces a follow-up note that adjusts T2/T4 to use the
fallback paths below.

**Fallback path 1: `BRepBuilderAPI_Sewing` missing** — likely unrecoverable
without an OCCT WASM rebuild. T1 must capture this and we pause v1 until
the bindings ship. Document the workaround (manual face stitching via
`BRep_Builder.Add(shell, face)`) but do NOT implement — it has a worse
robustness budget than `Sewing`.

**Fallback path 2: `BRepBuilderAPI_MakeSolid_1` missing** — recoverable via
`new oc.TopoDS_Solid()` + `new oc.BRep_Builder()` then
`builder.MakeSolid(solid); builder.Add(solid, shell)`. Adds ~10 LOC to T2,
no schema change.

**Fallback path 3: `BRepAlgoAPI_Common_3` missing** — the only path is a
custom build adding `Common_3` to the whitelist, OR emit `common` as
`cut(a, cut(a, b))` (a Boolean identity: `A ∩ B = A − (A − B)`). Either
works; the identity path is the v1 escape hatch.

### Sketch probe (for T1)

```js
// Logged once at worker boot, right after `oc = await initOcct()`.
function logBindingCoverage(oc) {
  const probe = [
    'BRepAlgoAPI_Common_3',
    'BRepBuilderAPI_Sewing',
    'BRepBuilderAPI_MakeSolid_1',
    'BRepBuilderAPI_MakeSolid_2',
    'BRep_Builder',
  ]
  const out = {}
  for (const name of probe) out[name] = typeof oc[name] !== 'undefined'
  // eslint-disable-next-line no-console
  console.info('[occt] binding coverage:', out)
  return out
}
```

## Design — `feature_to_solid` (op A′)

### LLM tool spec

```python
feature_to_solid_spec = ToolSpec(
    name="feature_to_solid",
    description=(
        "Append a `to_solid` node to a `.feature` file. Promotes the named "
        "feature's surface output (a TopoDS_Face / Shell / sewn-face collection) "
        "to a TopoDS_Solid via BRepBuilderAPI_Sewing + MakeSolid. Required as a "
        "preparatory step before `feature_boolean` can consume a surface body."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_id": {"type": "string", "description": "Existing feature node id whose output to promote."},
            "options": {
                "type": "object",
                "properties": {
                    "tolerance": {
                        "type": "number",
                        "description": "Sewing tolerance in model units (default 1e-6, raise for noisy NURBS).",
                    },
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_id"],
    },
)
```

### Feature-tree node shape

```json
{
  "id": "to_solid-1",
  "op": "to_solid",
  "target_id": "sweep1-3",
  "tolerance": 1e-6
}
```

### Worker handler — pseudocode

```js
// src/lib/occtWorker.js
function opToSolid(oc, _prev, node, _sketches, tracker, bodyMap) {
  const targetId = node.target_id
  if (!targetId) throw new Error('to_solid: target_id required')
  const target = bodyMap[targetId]
  if (!target) throw new Error(`to_solid: target ${targetId} not found in evaluated tree`)

  const tolerance = Number(node.tolerance) || 1e-6

  // Sew faces/shells into a closed shell.
  const sewing = track(tracker, new oc.BRepBuilderAPI_Sewing(tolerance, true, true, true, false))
  sewing.Add(target)
  sewing.Perform(new oc.Message_ProgressRange_1())
  const sewn = sewing.SewedShape()

  // Promote shell→solid.
  if (typeof oc.BRepBuilderAPI_MakeSolid_1 === 'undefined') {
    // Fallback path 2.
    const solid = track(tracker, new oc.TopoDS_Solid())
    const builder = track(tracker, new oc.BRep_Builder())
    builder.MakeSolid(solid)
    // sewn is a TopoDS_Shape — narrow to TopoDS_Shell via TopExp_Explorer.
    const exp = track(tracker, new oc.TopExp_Explorer_2(sewn, oc.TopAbs_ShapeEnum.TopAbs_SHELL, oc.TopAbs_ShapeEnum.TopAbs_SHAPE))
    if (!exp.More()) throw new Error('to_solid: sewing produced no shell')
    builder.Add(solid, exp.Current())
    return solid
  }

  const makeSolid = track(tracker, new oc.BRepBuilderAPI_MakeSolid_1())
  const shellExp = track(tracker, new oc.TopExp_Explorer_2(sewn, oc.TopAbs_ShapeEnum.TopAbs_SHELL, oc.TopAbs_ShapeEnum.TopAbs_SHAPE))
  if (!shellExp.More()) throw new Error('to_solid: sewing produced no shell — input may be open/non-manifold')
  makeSolid.Add(shellExp.Current())
  makeSolid.Build(new oc.Message_ProgressRange_1())
  if (!makeSolid.IsDone()) throw new Error('to_solid: MakeSolid failed')
  return makeSolid.Solid()
}
```

### Body-map plumbing (gotcha)

`opBlendSrf` already reads from `prev` because surface-producing ops chain
through the timeline like every other op. `opBoolean` and `opToSolid` need
**arbitrary** lookups (`target_id` can be any earlier node), so they
require an explicit `bodyMap: { [feature_id]: TopoDS_Shape }` populated as
the timeline evaluates. The existing `evaluateTree` doesn't carry a body
map today — T2 introduces it. Critical: stored shapes in the body map are
*aliases* of the in-flight `current` until the timeline moves past them;
the cleanup pass at the end of `evaluateTree` walks the map and frees
them. **Do not double-free** (`current === bodyMap[node.id]` for in-flight
nodes).

## Design — `feature_boolean` (op A)

### LLM tool spec

```python
feature_boolean_spec = ToolSpec(
    name="feature_boolean",
    description=(
        "Append a `boolean` node to a `.feature` file. Performs a CSG-style "
        "operation between two existing feature bodies. Both targets must "
        "resolve to TopoDS_Solid — if either is a surface, run "
        "`feature_to_solid` on it first."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_a_id": {"type": "string", "description": "First operand (the 'A' side; the one preserved on cut)."},
            "target_b_id": {"type": "string", "description": "Second operand (the 'B' side; the tool body on cut)."},
            "kind": {
                "type": "string",
                "enum": ["cut", "fuse", "common"],
                "description": "cut = A − B, fuse = A ∪ B, common = A ∩ B.",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_a_id", "target_b_id", "kind"],
    },
)
```

### Feature-tree node shape

```json
{
  "id": "boolean-1",
  "op": "boolean",
  "target_a_id": "pad-1",
  "target_b_id": "sweep1-3",
  "kind": "cut"
}
```

### Worker handler — pseudocode

```js
function opBoolean(oc, _prev, node, _sketches, tracker, bodyMap) {
  const a = bodyMap[node.target_a_id]
  const b = bodyMap[node.target_b_id]
  if (!a) throw new Error(`boolean: target_a ${node.target_a_id} not found`)
  if (!b) throw new Error(`boolean: target_b ${node.target_b_id} not found`)

  // Topology check: both must be SOLID. Surface bodies require feature_to_solid first.
  if (!isSolid(oc, a)) throw new Error(
    `boolean: target_a is a ${shapeKindName(oc, a)}, not a solid — run feature_to_solid on ${node.target_a_id} first`)
  if (!isSolid(oc, b)) throw new Error(
    `boolean: target_b is a ${shapeKindName(oc, b)}, not a solid — run feature_to_solid on ${node.target_b_id} first`)

  let algo
  switch (node.kind) {
    case 'cut':
      algo = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, b, new oc.Message_ProgressRange_1()))
      break
    case 'fuse':
      algo = track(tracker, new oc.BRepAlgoAPI_Fuse_3(a, b, new oc.Message_ProgressRange_1()))
      break
    case 'common':
      if (typeof oc.BRepAlgoAPI_Common_3 === 'undefined') {
        // Fallback path 3: A ∩ B = A − (A − B)
        const inner = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, b, new oc.Message_ProgressRange_1()))
        inner.Build(new oc.Message_ProgressRange_1())
        if (!inner.IsDone()) throw new Error('boolean: common-via-cut inner step failed')
        algo = track(tracker, new oc.BRepAlgoAPI_Cut_3(a, inner.Shape(), new oc.Message_ProgressRange_1()))
        break
      }
      algo = track(tracker, new oc.BRepAlgoAPI_Common_3(a, b, new oc.Message_ProgressRange_1()))
      break
    default:
      throw new Error(`boolean: unknown kind '${node.kind}' (expected cut|fuse|common)`)
  }
  algo.Build(new oc.Message_ProgressRange_1())
  if (!algo.IsDone()) throw new Error(`boolean: ${node.kind} algorithm failed (BOPAlgo error)`)
  const result = algo.Shape()
  // Sanity: empty result on common-of-non-touching solids is legal but worth surfacing.
  if (isEmptyShape(oc, result)) {
    throw new Error(`boolean: ${node.kind} produced an empty result (operands may not intersect)`)
  }
  return result
}
```

Helpers `isSolid`, `shapeKindName`, `isEmptyShape` already live (or have
near-twins) in `src/lib/occtBridge.js`; if not, T2 adds them.

## FeatureView inspector spec

Both ops register under the **Modify** category (`FEATURE_CATEGORIES` at
`src/components/FeatureView.jsx:357`). They sit next to `fillet` / `chamfer` /
`shell` / `push_pull` / `variable_radius_fillet`.

### `feature_to_solid` inspector

```js
{
  op: 'to_solid',
  label: 'To Solid',
  icon: Box,                       // or Layers if Box reads as a primitive
  defaults: { target_id: '', tolerance: 1e-6 },
  fields: [
    { key: 'target_id', kind: 'feature_picker', label: 'Surface body to cap' },
    { key: 'tolerance', kind: 'number', label: 'Sewing tolerance (mm)', min: 1e-9, step: 1e-7 },
  ],
}
```

### `feature_boolean` inspector

```js
{
  op: 'boolean',
  label: 'Boolean',
  icon: Combine,                   // or GitMerge
  defaults: { target_a_id: '', target_b_id: '', kind: 'cut' },
  fields: [
    { key: 'target_a_id', kind: 'feature_picker', label: 'A (kept on cut)' },
    { key: 'target_b_id', kind: 'feature_picker', label: 'B (subtracted on cut)' },
    { key: 'kind', kind: 'select', label: 'Operation', options: [
      { value: 'cut',    label: 'Cut (A − B)' },
      { value: 'fuse',   label: 'Fuse (A ∪ B)' },
      { value: 'common', label: 'Common (A ∩ B)' },
    ] },
  ],
}
```

The Modify category row becomes:

```js
{ id: 'modify', label: 'Modify',
  ops: ['fillet', 'chamfer', 'shell', 'push_pull', 'variable_radius_fillet',
        'to_solid', 'boolean'] }
```

## Error handling matrix

| Failure mode | Where caught | User-facing message | Code |
|---|---|---|---|
| `target_id` missing from `bodyMap` | `opToSolid` / `opBoolean` | `boolean: target_a 'sweep1-3' not found` | `BAD_INPUT` |
| Sewing produced no shell (open face network) | `opToSolid` | `to_solid: sewing produced no shell — input may be open/non-manifold` | `OP_FAILED` |
| `MakeSolid.IsDone()` false | `opToSolid` | `to_solid: MakeSolid failed` | `OP_FAILED` |
| Boolean on non-solid operand | `opBoolean` | `boolean: target_a is a SHELL, not a solid — run feature_to_solid on … first` | `BAD_INPUT` |
| `BRepAlgoAPI_*.IsDone()` false | `opBoolean` | `boolean: cut algorithm failed (BOPAlgo error)` | `OP_FAILED` |
| Common of non-touching solids | `opBoolean` | `boolean: common produced an empty result (operands may not intersect)` | `OP_FAILED` |
| Unknown `kind` | `opBoolean` schema gate + runtime | `boolean: unknown kind 'foo'` | `BAD_ARGS` |
| `BRepBuilderAPI_Sewing` not bound at boot | T1 probe | (no user-facing op yet) — pre-merge gate | n/a |

The python-side tool wrappers use the existing `err_payload(msg, code)`
helper from `kerf_chat.tools.registry` (template:
`run_feature_blend_srf` in `surfacing.py`). The worker-side errors propagate
via the existing `throw new Error(\`feature '${node.id}': ${msg}\`)` path
from `evaluateTree` (occtWorker.js:1482).

## Test plan

### Pytest (kerf-cad-core)

`packages/kerf-cad-core/tests/test_feature_to_solid.py` and
`test_feature_boolean.py`. Modelled on `test_feature_sweep1_mode.py`:
in-memory `FakePool` ctx, no DB, no OCCT required.

- Schema: `kind` accepts `cut|fuse|common`, rejects others, no default
  (required field).
- Schema: `feature_to_solid` `tolerance` defaults to 1e-6, accepts overrides.
- Schema: `target_a_id` / `target_b_id` / `target_id` required.
- Node-shape: written JSON matches the tree node spec above.
- Error wrappers: invalid JSON args → `BAD_ARGS`; missing `file_id` →
  `BAD_ARGS`; non-uuid `file_id` → `BAD_ARGS`; non-existent file →
  `NOT_FOUND`.

Expect ~12 cases per file, 24 total.

### Vitest (frontend)

`src/__tests__/featureBoolean.test.js`. Mirrors
`src/__tests__/featureSweep1Mode.test.js`:

- Worker dispatch: `op: 'to_solid'` reaches `opToSolid` in both
  `evaluateTree` and `evaluateToFinalShape`.
- Worker dispatch: `op: 'boolean'` reaches `opBoolean` in both eval paths.
- Inspector: defaults render; `target_a_id` + `target_b_id` populate via
  feature_picker.
- Inspector: `Modify` category contains `to_solid` + `boolean` entries.

Expect ~8 cases.

### Integration (OCCT-actual)

`src/__tests__/booleanIntegration.test.js` (gated by the same skip pattern
as `occtRunner.test.js` — only runs when WASM is fetchable). Three
end-to-end scenarios:

1. **Closed sweep1 cut by pad**: build `sweep1` of a circle along a
   straight path → already a solid (closed profile); `pad` of a rectangle
   that intersects it; `boolean(kind=cut)` produces non-degenerate
   mesh. Assert: vertex count > 0; bbox shrunk vs. original sweep1.
2. **`blend_srf` capped + cut**: build a small box, `blend_srf` between two
   edges, `to_solid` on the blend; `boolean(kind=fuse)` with another box.
   Assert: final shape is a single connected solid with > face_count of
   either operand.
3. **Negative path**: try `boolean` on a `blend_srf` face directly (no
   `to_solid`). Assert error message contains the hint
   `"run feature_to_solid on … first"`.

Expect ~10 assertions total.

## Task breakout

Tasks are sized for a single sonnet agent each (≤1 file family per task
where possible). Dependency graph:

```
       ┌─ T1 ──┐
       │       │
       ▼       ▼
       T2      (T1 outcome may revise T2/T4 to fallback paths)
       │
       ├── T3
       │
       └── T4
           │
           ├── T5
           │
           └── T6
               │
               └── T7
```

### T1 — Binding probe + `surfaceToSolid` helper · ~1 day · gating

Add a one-shot binding-coverage probe to `loadOcct()` boot in
`src/lib/occtWorker.js` (template: existing `defensiveProbe` patterns).
Probe `BRepAlgoAPI_Common_3`, `BRepBuilderAPI_Sewing`,
`BRepBuilderAPI_MakeSolid_1`. Log results once via `console.info`.

Add `surfaceToSolid(oc, shape, tracker, { tolerance = 1e-6 } = {})` helper
to `src/lib/occtBridge.js` next to `ringsToFace`. Implements the pseudocode
above; throws on missing bindings.

Output: probe report (which bindings exist on the running build). If
`Sewing` is missing, **STOP** and escalate — v1 needs an OCCT WASM
rebuild before T2+ proceed. If `MakeSolid_1` is missing, switch T2 to
use the fallback path. If `Common_3` is missing, switch T4 to use the
cut-of-cut identity.

Deps: none.

### T2 — `opToSolid` worker handler + dispatch wiring · ~1 day

Add `opToSolid(oc, _prev, node, _sketches, tracker, bodyMap)` to
`src/lib/occtWorker.js`. Wire `case 'to_solid'` into **both** `evaluateTree`
and `evaluateToFinalShape` switches (occtWorker.js:1386 and :1514). Follow
the dispatch pattern from `opBossWithDraft` — finalize `current` if it
exists (`to_solid` is a *new* body, not a chained modification), push to
meshes, cleanup, then evaluate. **Avoid the dormant-node bug** that bit
boss_with_draft when a new-body op was only wired into one switch.

Plumb the `bodyMap` parameter: declare it locally at the top of each
evaluator (`const bodyMap = {}`), populate after each op finishes
(`bodyMap[node.id] = next`), free entries on `cleanupShape`. Pass `bodyMap`
into the surfacing-and-boolean ops only (keep older ops' signatures
unchanged to avoid touch-everywhere refactor).

Deps: T1.

### T3 — `feature_to_solid` Python LLM tool · ~0.5 day

Add `feature_to_solid_spec` + `run_feature_to_solid` to
`packages/kerf-cad-core/src/kerf_cad_core/surfacing.py` (template:
`run_feature_blend_srf`).

Register in `_TOOL_MODULES` list in `kerf-cad-core/plugin.py`.

Add a brief LLM doc page `packages/kerf-chat/llm_docs/feature_to_solid.md`
(template: `feature_sweep1.md`).

Deps: none (the python tool is pure feature-file mutation — no OCCT
involvement; worker-side runs T2's code).

### T4 — `opBoolean` worker handler · ~1 day

Add `opBoolean(oc, _prev, node, _sketches, tracker, bodyMap)` to
`src/lib/occtWorker.js` next to `opToSolid`. Switch on `node.kind`,
dispatch to `BRepAlgoAPI_Cut_3` / `Fuse_3` / `Common_3` (or fallback
identity if T1 flagged `Common_3` missing).

Wire `case 'boolean'` into **both** evaluator switches (same dispatch-
pattern care as T2). Boolean is a new body (finalize+cleanup current
before evaluating).

Deps: T2.

### T5 — `feature_boolean` Python LLM tool · ~0.5 day

Add `feature_boolean_spec` + `run_feature_boolean` to `surfacing.py`.
Register in plugin. LLM doc page `feature_boolean.md`.

Deps: none functionally (mirrors T3). Listed after T4 for psychological
ordering with the design doc.

### T6 — FeatureView inspector entries · ~1 day

Add `to_solid` + `boolean` entries to `FEATURE_KINDS` in
`src/components/FeatureView.jsx` (template lines 145–353). Add both ops
to the `Modify` category (`FEATURE_CATEGORIES`, line 359). Pick icons
from `lucide-react` (the existing import block); `Box` for to_solid,
`Combine` for boolean are good first choices.

Deps: T2, T4 (op must exist worker-side before the UI emits it).

### T7 — Pytest + vitest + integration test · ~1 day

Three test files per the test plan above. Pytest schema/error coverage,
vitest dispatch + inspector coverage, integration WASM test gated as in
`occtRunner.test.js`.

Deps: T3, T5, T6.

## Estimated total effort

| Task | Days |
|---|---|
| T1 | 1.0 |
| T2 | 1.0 |
| T3 | 0.5 |
| T4 | 1.0 |
| T5 | 0.5 |
| T6 | 1.0 |
| T7 | 1.0 |
| **Total** | **6.0** |

Matches the scoping doc's "~2-3 weeks" framing — most of the extra
calendar-time was schedule slack for binding rebuilds, which T1's probe
resolves on day one. If `BRepBuilderAPI_Sewing` is missing, add **~2
weeks** for an OCCT WASM rebuild before T2 can start.

## Highest-risk open question

**Boolean-failure modes on sewn-from-surfaces solids.**

The `BRepBuilderAPI_Sewing` + `MakeSolid` chain in `opToSolid` produces a
`TopoDS_Solid` that's *topologically* valid (closed shell, oriented faces)
but may carry tolerance imperfections inherited from the source NURBS
patches. When this solid then participates in `BRepAlgoAPI_Cut` with a
prismatic body, the section-curve step can fail along seams where the
sewing tolerance was tight relative to the boolean tolerance.

Symptoms to watch for in T7's integration test:
- `Cut.IsDone() === false` with no specific error code.
- `Cut.Shape()` is non-empty but visibly corrupt (missing faces, slivers).
- Result triangulation has degenerate triangles.

**Mitigation path (NOT v1 scope)**: expose `SetFuzzyValue` on the
boolean's `BOPAlgo_Builder` so callers can dial tolerance. The scoping
doc flags this as scope-C territory; v1 ships without it and we add it as
a 📋 next iff the integration test reveals systematic failures.

**Lighter mitigation (in v1 scope, only if T7 demands)**: raise the
`tolerance` parameter default on `feature_to_solid` from 1e-6 to 1e-4 if
empirical results show 1e-6 is unforgivingly tight. This stays a single
schema knob and avoids the binding question.

## What's intentionally NOT here

Carried over from the scoping doc, restated for the record:

- **Trim-by-curve on a single NURBS face** (scope B) — `BRepFeat_SplitShape` + `BRepProj_Projection` path. Bindings unverified, fragility budget unbounded. Stays deferred.
- **NURBS-NURBS robustness corpus** (scope C) — `SetFuzzyValue` + `ShapeFix_Shape` pre-pass + pathological-case test corpus. The famous "1-6 months" work the original ROADMAP framing refers to.
- **`matchSrf` / G3 continuity** — surface-edge matching for Class-A applications.
- **Mesh-CSG bridge** (scope D) — already half-shipped via the
  cross-kernel assembly path; needs doc-only discoverability work and
  doesn't belong on the v1 critical path.

If user demand for any of the above surfaces *during* v1 implementation,
add a separate plan doc — don't widen this one.
