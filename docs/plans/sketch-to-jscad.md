# Sketch → JSCAD workflow

> **Status:** planned (no code yet). Mesh-side analog of the existing
> `.sketch → .feature` BRep path.

## Motivation

Today the chat-LLM has two ways to produce 3D parts:

1. **`.feature` route** — `sketch_*` tools build a constrained 2D profile;
   `feature_pad` / `feature_pocket` / `feature_revolve` consume the sketch by
   `sketch_id`; OCCT computes a precise BRep. Requires the OCCT WASM build to
   be loaded and capable of the requested op.
2. **`.jscad` route** — `write_file` / `edit_file` emit raw JSCAD source. The
   AI is forced to type numerical primitives (`cuboid({ size: [40, 40, 10] })`,
   `cylinder({ radius: 6, height: 20 })`) and reason about positions in
   absolute coordinates.

Path (2) is verbose and error-prone for anything more elaborate than a
primitive — picture a bracket with three mounting holes at given pitch and a
chamfered ear. Writing that in raw JSCAD requires the LLM to do trig by hand;
writing it as a `.sketch` + a one-line `extrudeLinear` is dramatically
shorter, more legible, and the dimensions become editable in the sketcher
UI.

**This workflow** lets the user (or AI) draw a constrained 2D profile with
real dimensions, then ask the AI to "build the 3D part on top of this
sketch." The output is a `.jscad` file that imports the sketch and applies
JSCAD operations. The sketch remains the source of truth: editing a
dimension in the sketcher reflows the 3D.

Why this beats `.feature` for some users:
- JSCAD is fully programmable (loops, parametric variants, `colorize`,
  `hull`, mesh-only operations).
- No OCCT WASM dependency — works on the leanest local install.
- Iteration is faster (mesh booleans are cheaper than BRep booleans).

Why `.feature` still wins for others:
- Precise BRep, lossless STEP export, real fillets, manufacturer-grade
  tolerances.
- See [Comparison](#comparison-with-feature-route).

## Audit findings

### JSCAD evaluator (`src/lib/jscadRunner.js`, `jscadWorker.js`)

- Source runs in a Web Worker (`jscadWorker.js`); falls back to main thread
  if the worker can't spin up (Node test env, fatal worker error).
- The `@jscad/modeling` namespace is injected as `modeling`; commonly-used
  sub-namespaces (`primitives`, `transforms`, `booleans`, `extrusions`,
  `expansions`, `measurements`, `colors`, `utils`, `maths`, `curves`,
  `geometries`, `hulls`, `text`) are spread into the user's destructurable
  scope.
- `params` arg is injected from the merged `.equations` scope **plus** the
  active configuration's `params` map (config wins on collision; see
  `runJscad(code, configParams)` and `refreshEquationsCache` in
  `src/store/workspace.js`).
- **Sketch imports already work** via a top-level `import` form only —
  `SKETCH_IMPORT_RE = /^[ \t]*import\s+(\w+)\s+from\s+['"]([^'"]+\.sketch)['"]/`.
  The main thread resolves each `.sketch` path through a `sketchResolver`
  registered by the workspace store, parses it with `parseSketch`, converts
  to a JSCAD Geom2 via `sketchToGeom2`, and passes the Geom2 to the worker
  as a `sketchProfiles` payload — already structured-clone safe (plain
  arrays + numbers). The worker injects each binding into the eval scope.
- **`require('/x.sketch')` does NOT work** despite what `llm_docs/jscad.md`
  documents — the runner does not implement CommonJS `require` resolution.
  Only ES-module `import default from '/x.sketch'` is supported. (Fix in
  task breakout below.)
- `setSketchResolver(fn)` and `setEquationsResolver(fn)` are global mutables
  that decouple the runner from the workspace store (avoids a circular
  import). `findFileByPath` in `workspace.js` is the project-tree resolver
  the registered closure uses.

### Sketch internals (`packages/kerf-cad-core/src/kerf_cad_core/sketch.py`, `src/lib/sketchSolver.js`, `src/lib/sketchGeom2.js`)

- **Schema (`parseSketch` in `sketchSolver.js`):**
  ```js
  {
    version, plane: {type:'base'|'face', name|frame},
    entities: [{id, type:'point'|'line'|'arc'|'ellipse'|'bspline',
                construction?:bool, ...geometry}],
    constraints: [{id, type, ...refs, value?, params?:{}}],
    visible_3d: [],
    solved: {},  // last solver output, cached for warm boot
    metadata: {name?, description?},
    default_config?: string,
    configurations?: [{id, label, params:{}}],  // per-sketch param overrides
  }
  ```
- **Dimensional constraints** carry `value` as either a number or a string
  with `${name}` placeholders. The merged `.equations` scope resolves
  placeholders before the planegcs solver runs.
- **Sketch configurations** override the `.equations` scope inside the
  sketch (sketch config wins on collision) — the same shape as `.feature` /
  `.part`.
- **No top-level "named dimensions" map.** A sketch's parametric dimensions
  are just constraint values that reference `${equationName}`. So
  "dimension propagation" is already handled by `.equations` being shared
  with JSCAD via `params`. Renames of an equation flow through everywhere.
- **`sketchToGeom2`** (frontend, `src/lib/sketchGeom2.js`) walks
  non-construction entities, builds adjacency, finds closed loops,
  tessellates arcs (5°/segment), ellipses, b-splines (16 samples), groups
  outers + holes by ray-casting, and emits a JSCAD `Geom2`. Empty / open
  profiles return an empty `geom2.create([])` plus a `console.warn`.

### LLM tool surface (`sketch_*` tools)

Existing tools (live in `packages/kerf-cad-core/src/kerf_cad_core/sketch.py`):
- `sketch_add_entity` — line / arc / circle / ellipse / bspline / point
- `sketch_add_constraint` — geometric or dimensional
- `sketch_set_constraint_value` — dimensional values (mm) or `${param}`
- `sketch_delete_entity`
- `sketch_carbon_copy`
- `sketch_validate`

Plus `create_sketch` (in `packages/kerf-api/src/kerf_api/tools/scaffold.py`)
which scaffolds an empty `.sketch` file on a chosen plane.

These continue to work unchanged — the new tool only adds the 3D step.

### `.feature` precedent

`feature_pad` / `feature_pocket` / `feature_revolve` / `feature_rib` etc.
take a `sketch_id` (entity id inside a `.feature` file's embedded sketch
list) or a `sketch_file_id` (absolute path to an external `.sketch` file —
see `curve_ops.py`). The new tool will use the **path** form
(`sketch_file_id`) because the produced `.jscad` references the sketch by
path in its `import` statement, and a free-standing `.sketch` file is the
canonical input.

## Runtime helper design

**Decision: keep the existing `import profile from '/path.sketch'` form as
the only API.** No new globals, no `kerf.sketches.load(...)`. Rationale:

1. The import form is already wired end-to-end (worker passes through,
   re-eval semantics work, structured-clone-safe transfer).
2. The `import` form is statically inspectable by tools — the file tree can
   render the link without running the JSCAD.
3. A `kerf.*` namespace would require either a synchronous resolver
   (breaks the worker boundary) or async helpers (forces every JSCAD
   author to `await`).
4. JSCAD's modeling primitives consume the Geom2 directly; the user never
   needs to "unpack" it.

**Two ergonomic gaps to close** (small follow-ups, not new APIs):

a. **Document only the working form.** `llm_docs/jscad.md` currently shows
   `const profile = require('/x.sketch')` which does not work. Replace with
   the ES `import` form. (Task in breakout.)

b. **Fix the resolver error model.** Today an unresolved path emits a
   `console.warn` and returns an empty Geom2 — the JSCAD silently runs
   with a non-profile. Better: surface the error to `partsError` so the
   editor renders "sketch `/foo.sketch` not found" instead of a blank
   viewport. (Task in breakout.)

### Error model

- Missing file → JSCAD eval error `sketch '/foo.sketch' not found` (surfaced
  to `partsError`, shown in the problem panel).
- Empty / no-closed-loops sketch → empty Geom2, `console.warn`, but eval
  continues. Same as today (the user is mid-draw).
- Sketch with parse error → caller's responsibility (`parseSketch` already
  tolerates malformed JSON by returning a default skeleton). The viewport
  shows the JSCAD eval error against the empty geom.

### Fetch + cache semantics

- The store's `findFileByPath(files, path)` walks the file tree in O(N).
  Acceptable for projects with thousands of files.
- The runner does NOT cache parsed sketches — every `runJscad` call
  re-fetches and re-parses. That's the right default: a sketch edit must
  propagate. Caching is a future optimisation (key by file_id + content
  hash).

## LLM tool spec

### `extrude_sketch_to_jscad`

Best-fit name: makes the action explicit (extrude → emit JSCAD) and signals
that the produced file references the sketch. Alternative names rejected:
- `create_jscad_from_sketch` — too generic; doesn't hint at the 3D op
- `sketch_to_jscad` — looks like a converter (suggests sketch is
  destroyed)

```python
extrude_sketch_to_jscad_spec = ToolSpec(
    name="extrude_sketch_to_jscad",
    description=(
        "Scaffold a new .jscad file that imports a .sketch profile and "
        "applies an extrusion to produce a 3D part. The sketch remains "
        "the source of truth — editing its dimensions reflows the 3D. "
        "Supported ops: 'extrude_linear' (linear pad), 'extrude_rotate' "
        "(revolve around an in-plane axis), 'sweep_along_path' (sweep "
        "the profile along a second sketch's open path). For boolean ops "
        "(boss/cut), compose two extrudes manually via edit_file after "
        "scaffolding. For real B-rep + STEP export, use create_feature + "
        "feature_pad instead — see docs/llm/feature.md."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path for the new .jscad file."
            },
            "sketch_file_id": {
                "type": "string",
                "description": "Absolute path to the .sketch profile, "
                                "e.g. '/parts/bracket-outline.sketch'."
            },
            "operation": {
                "type": "string",
                "enum": ["extrude_linear", "extrude_rotate", "sweep_along_path"],
                "description": "Which JSCAD op to apply."
            },
            "params": {
                "type": "object",
                "description": (
                    "Op-specific. extrude_linear: {height_mm | "
                    "height_param} (height_param refers to an "
                    ".equations name). extrude_rotate: {angle_deg, "
                    "segments?}. sweep_along_path: {path_sketch_file_id}."
                )
            },
            "object_id": {
                "type": "string",
                "description": "Id of the produced JSCAD Object; defaults "
                                "to the sketch's basename."
            },
        },
        "required": ["path", "sketch_file_id", "operation", "params"]
    },
)
```

**Behaviour:**
- Validates that the sketch file exists and parses.
- Validates that the operation's `params` reference valid equation names
  if `*_param` form is used.
- Emits a small `.jscad` source:
  ```js
  // Generated from /parts/bracket-outline.sketch — edit the sketch
  // to change dimensions; the 3D updates automatically.
  import profile from '/parts/bracket-outline.sketch'

  export default function ({ extrusions, params }) {
    const body = extrusions.extrudeLinear({ height: params.bracket_h }, profile)
    return [{ id: 'bracket', geom: body }]
  }
  ```
- Returns `{path, id, sketch_file_id, operation}` so the chat can confirm.

**Why this beats raw `write_file` for the LLM:**
- Pre-fills the boilerplate (import statement, default export, return shape).
- Validates the sketch exists *before* the file is created.
- Encodes the canonical pattern so the user always sees the same shape
  across projects (greppable, comparable).
- The model still has `write_file` / `edit_file` for arbitrary follow-up
  edits (add a second extrude, boolean two parts together, colorize) —
  this tool is *scaffolding*, not a one-shot.

### Sample model invocation

User: "make a 10mm-thick plate from that outline I drew"

Model call:
```json
{
  "name": "extrude_sketch_to_jscad",
  "input": {
    "path": "/parts/plate.jscad",
    "sketch_file_id": "/parts/plate-outline.sketch",
    "operation": "extrude_linear",
    "params": {"height_mm": 10},
    "object_id": "plate"
  }
}
```

### `extend_jscad_with_sketch_op` (out of scope for v1)

A second tool that appends an op to an existing `.jscad` that already
references the sketch (or pulls in a new sketch) was considered. Decision:
**defer**. The model can already use `edit_file` against a known-shape
generated file to add a second extrude + a `booleans.subtract`. Adding a
dedicated tool ahead of evidence that the LLM struggles is over-engineering.

## Bidirectional source-of-truth flow

### Sketch edit (UI) → JSCAD re-eval

**Gap today:** when the user edits a sketch in `SketchView`, `updateSketch`
in `workspace.js` persists the new content but does NOT trigger a re-run of
any open `.jscad` file that imports it. The currently-open file is the
sketch itself; the importer is in a different file, possibly not even
loaded.

**Fix:** when an open `.jscad` file is being viewed and the user edits a
sketch in a side-by-side editor (future split-pane) OR the LLM edits a
sketch via `sketch_*` tools while a `.jscad` is open:
1. Extend `updateSketch` to find all `.jscad` files in the project whose
   content matches `SKETCH_IMPORT_RE` against the edited sketch's path.
2. If the currently-open file is one of them, call `runJscad` with the new
   sketch content.
3. (Cache invalidation for `componentResultCache` if the sketch is part of
   an assembly chain.)

For v1 a smaller fix is enough: only the **currently-open** `.jscad` is
re-run, and we just check whether its source imports the edited sketch.
Cross-file invalidation is a follow-up.

### AI sketch edit → JSCAD re-eval

`sketch_*` tools run on the backend; the frontend gets the updated content
via the standard `files` PATCH path. The websocket/poll-based refresh
already updates `currentFileContent` and re-renders the sketch. We need
the same hook as above to also re-run the open `.jscad` if it imports the
mutated sketch.

### Dimension propagation

Already works via `.equations`. A sketch dimensional constraint of
`${wall_thickness}` reads from the merged equations scope; the JSCAD's
`params.wall_thickness` reads from the same scope. Renaming `wall_thickness`
in the equations file breaks both sites — the sketch reports an unresolved
placeholder, the JSCAD reports `params.wall_thickness is undefined`.
Both errors are useful.

**Open question:** should the new tool *generate JSCAD code that reads from
`params`*, or hard-code numerics? The spec above lets the caller pick
(`height_mm` literal vs `height_param` equation reference). Default-to-
literal because the simplest path is `height: 10`; opt into parametric
only when the model knows an equation already exists.

## Comparison with `.feature` route

| Aspect              | `.sketch + .jscad` (this plan)         | `.sketch + .feature` (existing)             |
|---------------------|-----------------------------------------|---------------------------------------------|
| Geometry kernel     | JSCAD CSG (mesh booleans)               | OCCT (B-rep)                                |
| STEP export         | Tessellated (lossy)                     | Lossless                                    |
| Real fillets        | No (`hull` / rounded-cuboid only)       | Yes (`feature_fillet`)                      |
| Programmability     | Full JS (loops, conditionals, recursion)| JSON tree; loops via configurations         |
| Local dep           | None — pure JS                          | OCCT WASM (~6 MB)                           |
| Eval cost           | ms-scale                                | 10s of ms to seconds                        |
| Manufacturing-grade | No (mesh tolerances)                    | Yes                                         |
| Surfacing           | Limited                                 | NURBS sweep/network/blend                   |

**LLM guidance to add in `docs/llm/jscad.md`:**

> Pick `.feature` when the user mentions STEP export, manufacturing,
> fillets, chamfers, draft angles, or interop with FreeCAD / SolidWorks.
> Pick `.sketch + .jscad` (this workflow) when the user wants quick
> parametric variants, mesh-only ops (`hull`, `colorize`, instancing),
> or has no OCCT installed.

## Migration / file-kind impact

- **No new file kinds.** The output is a regular `.jscad`.
- **No new schema fields.** The `.sketch` file is untouched.
- **No DB migration.** The link is encoded in the `import` statement
  inside the `.jscad` source.
- **File tree backlink rendering** is a frontend-only enhancement; no DB
  index needed for v1 (the project tree is in-memory; scanning content
  is cheap at the scale of a project).

## Frontend UX recommendation

### "Build 3D" button in SketchView (v1)

Add a small dropdown button to the SketchView toolbar:
- **"Extrude →" (height input)** → calls `extrude_sketch_to_jscad` with
  `operation=extrude_linear` and the typed height; creates the `.jscad`
  alongside the sketch in the file tree; opens the new file.
- **"Revolve →" (angle input)** → same with `operation=extrude_rotate`.
- **"Pad / Pocket / Revolve (BRep)…"** — separator + existing `.feature`
  toolbar entries.

This is the UX that mirrors FreeCAD's "active body" affordance described
in the existing "FreeCAD parity: sketch → 3D shortcuts" ROADMAP row.

### File tree backlink

When a `.jscad` imports a `.sketch`, render a small `← from <basename>.sketch`
chip on the JSCAD row (subtle, hover-only). Future: invert direction —
sketch rows show "used by 2 parts". Skip for v1 unless cheap.

### Reactive re-eval

When a `.jscad` file is open and a sketch it imports is saved (either by
the SketchView or by an LLM `sketch_*` tool), re-run JSCAD automatically.
Hook into `workspace.updateSketch` and the post-tool-message refresh
pipeline. Single content match check, no full project scan.

## Task breakout

Each task sized for one Sonnet-agent ≈ 1 day. ~5 tasks total.

### Task 1 — Document the working sketch-import form
**File:** `packages/kerf-chat/llm_docs/jscad.md`
- Replace `const profile = require('/x.sketch')` with the working
  `import profile from '/x.sketch'` form (the current docs are wrong —
  the runtime only implements the ES-module shape).
- Add a section "Importing equations as `params`" describing the
  `params.foo` injection from `.equations`.
- Add a "Choosing between `.jscad` + sketch and `.feature` + sketch"
  comparison table.

### Task 2 — Implement `extrude_sketch_to_jscad` LLM tool
**Files:** `packages/kerf-cad-core/src/kerf_cad_core/sketch.py` (or a new
sibling `packages/kerf-cad-core/src/kerf_cad_core/jscad_scaffold.py`).
- New `ToolSpec` per the spec above.
- Validation: sketch exists, sketch parses to ≥ 1 closed loop, target
  path doesn't collide, op + params match the schema.
- Emits canonical JSCAD source via templated f-string per op.
- Pytest coverage: happy path per op, missing sketch, malformed sketch,
  bad params, target-exists collision.

### Task 3 — Surface sketch-import errors in JSCAD viewport
**Files:** `src/lib/jscadRunner.js`, `src/store/workspace.js`.
- `resolveSketchImports` currently swallows missing files. Promote
  unresolved paths to a thrown error so `runJscad` reports it via
  `partsError`.
- Vitest covering the error path.

### Task 4 — Reactive re-eval when imported sketch changes
**Files:** `src/store/workspace.js`.
- After `updateSketch` persists, if the currently-open file is a `.jscad`
  whose source matches `SKETCH_IMPORT_RE` against the edited sketch's
  path, call `runJscad` and replace `parts`.
- Same hook on the post-LLM-tool-message refresh path (so `sketch_*` tool
  calls reflow the 3D).
- Vitest covering both flows.

### Task 5 — "Build 3D" SketchView affordance + file-tree backlink
**Files:** `src/components/SketchView.jsx`, `src/components/FileTree.jsx`.
- "Extrude →" / "Revolve →" dropdown on the SketchView toolbar; wires
  through the chat surface to invoke `extrude_sketch_to_jscad`.
  (Implementation note: the simplest wiring is a synthetic chat message
  that the agent handles; an inline RPC is fine too if a `/v1/rpc`
  method exists for the tool. Tool dispatch already supports this.)
- File-tree row: when a `.jscad` source imports a sketch, render a
  small "← <sketch-name>" chip.
- Vitest snapshot for the toolbar; integration test for the chip.

## Open architectural questions

1. **Cross-file invalidation.** When sketch `A.sketch` is edited and is
   imported by `B.jscad` which is imported by `C.jscad` which is
   referenced by `D.assembly`, what gets re-evaluated? v1 only re-runs
   the open file; full graph invalidation (with `componentResultCache`
   busting) is a follow-up — track scope in a dedicated row.
2. **`require()` legacy.** The docs hinted at `require('/x.sketch')` —
   should we *also* implement that for ergonomic parity? Verdict from
   this plan: no, because ES `import` is statically inspectable; add
   `require` only if a real user file is found that uses it.
3. **Sketch-config awareness from JSCAD.** A sketch can carry
   `configurations[]`. Today the JSCAD scope receives a single resolved
   Geom2 — there's no way for the JSCAD to switch the sketch's
   configuration. Should `extrude_sketch_to_jscad` accept a
   `sketch_config_id` and bake it in? Probably yes (v1.1) — emit
   `import profile from '/x.sketch?config=heavy-duty'` and have the
   resolver pass the config to `parseSketch`. Out of scope for v1.
4. **Hot-reloaded equations.** When `params.height` changes via the
   equations editor, both the sketch's dimensional constraint *and*
   the JSCAD's `extrudeLinear({height: params.height}, profile)` should
   update on the same tick. Today `refreshEquationsCache` triggers a
   single `runJscad` call. Verify the sketch profile is also resolved
   with the latest equations scope — the sketch solver does this via
   `numericValue`, but the path through `sketchToGeom2` does not re-solve;
   it reads `solved` from the sketch JSON. Need to verify this is
   updated on equation changes. (Could be a hidden bug, or could already
   be handled — audit during Task 3.)
5. **Multi-sketch ops.** A sweep needs two sketches (profile + path).
   The `sweep_along_path` operation in the tool spec covers this, but
   the runtime helper (the `import` form) only resolves one binding per
   line. Multiple lines work fine, so the generated JSCAD will look like:
   ```js
   import profile from '/sweep-profile.sketch'
   import railPath from '/sweep-rail.sketch'  // open polyline; non-closed
   ```
   But `sketchToGeom2` returns an empty Geom2 for open profiles. We need
   a `sketchToPath` helper for open paths. Possibly out of scope for v1
   if we ship only extrude_linear + extrude_rotate first.

## Estimated effort

5 tasks × ~1 sonnet-day each = **~5 sonnet-agent-days** end-to-end.
Tasks 1–3 are independent and parallelisable; tasks 4 + 5 depend on 2.
