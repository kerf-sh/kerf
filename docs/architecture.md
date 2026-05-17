# Architecture

How Kerf is wired end to end — from a chat message to a re-rendered model.

## The big picture

```
┌───────────────────────────┐         ┌──────────────────────────────┐
│        Browser            │         │     Python server (kerf)      │
│                           │         │                              │
│  React + Vite + Three.js  │ ◄─────► │  FastAPI · asyncpg · auth     │
│  Monaco · planegcs · OCCT │   HTTP  │  Storage · LLM clients       │
│  IndexedDB mesh cache     │         │  Plugin loader · /health/caps│
│  Web Worker (JSCAD eval)  │         │  Tool registry · Agent loop  │
└───────────────────────────┘         └──────────────┬───────────────┘
                                                     │
                                        ┌────────────┴─────────────┐
                                        │     Postgres (asyncpg)   │
                                        │  users / projects /      │
                                        │  files / file_revisions  │
                                        │  chat_threads / messages │
                                        └────────────┬─────────────┘
                                                     │
                                        ┌────────────┴─────────────┐
                                        │   Storage (local/s3/git) │
                                        │  STEP files, chunks,     │
                                        │  cloud thumbnails        │
                                        └──────────────────────────┘
```

Single binary. Single Postgres. Pluggable storage. Pluggable LLM provider.
Plugins discovered from Python entry points at startup.

## Stack

- **Frontend**: Vite 8 + React 19 + React Router 7 SPA. Tailwind v4. Zustand state.
  Three.js r160 3D viewport with BVH raycaster + frustum culling + `InstancedMesh`
  batching. `@jscad/modeling` 2.x in a Web Worker for non-blocking mesh eval.
  `@salusoft89/planegcs` sketch solver. `occt-import-js` STEP loader. IndexedDB
  mesh cache keyed by JSCAD content hash.
- **Backend**: Python FastAPI in `packages/kerf-core/src/kerf_core/app.py`.
  asyncpg + SQLAlchemy (async). JWT + opaque API tokens. Google OAuth via
  `authlib`. TOML config (`tomllib`/`tomli`). Provider-agnostic LLM ABC with
  concrete clients for Anthropic, OpenAI, Moonshot, Gemini in `packages/kerf-chat/`.
- **Compute**: every heavy task lives inside a plugin (`kerf-fem`, `kerf-cam`,
  `kerf-topo`, `kerf-render`, `kerf-electronics`, …). Long-running jobs are
  managed by `kerf-workers` (`workers.harness`). No separate sidecar process —
  workers run in-process or as a `compute-only` install.
- **Storage**: See §Storage abstraction.

## Plugin architecture

Kerf is a meta-package (`pyproject.toml` at the repo root) that pulls one of
six **persona** bundles of plugins:

```
api-only · mech · electronics · bim · full · compute-only
```

Each persona is an optional-dependency group naming a subset of the 19 plugin
packages under `packages/`. Plugins register themselves as Python entry points
under the `kerf.plugins` group:

```toml
# packages/kerf-cad-core/pyproject.toml
[project.entry-points."kerf.plugins"]
cad-core = "kerf_cad_core.plugin:register"
```

### Boot sequence (`kerf_core.app.create_app`)

1. Load TOML config.
2. Build the **PluginContext** (asyncpg pool, storage backend, tool registry,
   worker registry, logger, `cloud_enabled`, `local_mode`).
3. `importlib.metadata.entry_points(group="kerf.plugins")` — discover every
   installed plugin in the active virtualenv.
4. Call each plugin's `register(app, ctx)` in dependency order. Each plugin
   mounts its routers, registers its LLM tools into `ctx.tools`, and returns a
   `PluginManifest`.
5. Aggregate manifests onto `app.state.loaded_plugins` and mount
   `/health/capabilities` for runtime introspection.
6. Start every registered worker via `ctx.workers.start_all()`.

### Contract: PluginContext + PluginManifest

```python
# packages/kerf-core/src/kerf_core/plugin.py

@dataclass
class PluginContext:
    pool: asyncpg.Pool
    storage: StorageBackend
    config: Config
    tools: ToolRegistry
    workers: WorkerRegistry
    logger: structlog.BoundLogger
    cloud_enabled: bool
    local_mode: bool

@dataclass
class PluginManifest:
    name: str
    version: str
    provides: list[str] = []
    depends: list[str] = []
```

`provides` is a list of capability tags (e.g. `cad.step-io`,
`fem.linear-static`). The full taxonomy and per-plugin tags live in
[capabilities.md](./capabilities.md). `depends` is by plugin name and is used
purely for ordering.

### Per-plugin layout

Every plugin in `packages/kerf-<name>/` follows the same shape:

```
packages/kerf-<name>/
├── pyproject.toml         # name, version, entry-point, deps
├── src/kerf_<name>/
│   ├── __init__.py
│   ├── plugin.py          # register(app, ctx) → PluginManifest
│   ├── routes*.py         # FastAPI routers (optional)
│   ├── tools/             # LLM-tool modules registered into ctx.tools
│   └── llm_docs/          # corpus markdown shipped to the LLM (optional)
└── tests/                 # pytest suite, auto-discovered from root
```

The library plugins (`kerf-cad-core`, `kerf-tess`) mount no routes — they are
pure Python APIs other plugins import. Service plugins (`kerf-api`,
`kerf-electronics`, …) mount routes + register tools.

### Capability tags at runtime

```
GET /health/capabilities
```

returns the union of every loaded plugin's `provides` list plus per-plugin
metadata. The frontend uses this to decide which UI surfaces to render; other
plugins use it for conditional behaviour. Full reference: [capabilities.md](./capabilities.md).

## Frontend (detail)

A 4-tier debounce throttles JSCAD re-eval based on file size: 250 ms for tiny
files up to ~3 s for huge ones, so the viewport stays responsive whatever
the source size.

Three.js scene is built with frustum culling (S1) and `InstancedMesh` batching
(S2) — assemblies with hundreds of identical components render at interactive
frame rates.

## File kinds

Kerf supports **40+ file kinds**. Each kind has a dedicated schema doc in a
plugin's `llm_docs/<kind>.md` (consulted by the LLM via `search_kerf_docs`
before authoring or editing that kind).

| Kind | Purpose | Plugin |
|------|---------|--------|
| `.jscad` | Code-driven mesh via JSCAD scripting | kerf-chat / kerf-api |
| `.feature` | OCCT B-rep feature tree (pad/pocket/fillet/etc.) | kerf-cad-core + kerf-imports |
| `.sketch` | 2D constraint-managed geometry (planegcs) | kerf-cad-core |
| `.assembly` | BOM-driven product structure | kerf-api + kerf-mates |
| `.drawing` | Multi-sheet manufacturing drawings with GD&T | kerf-imports |
| `.part` | Library part with MPN, distributors, photos | kerf-api + kerf-cloud |
| `.circuit.tsx` | tscircuit electronics (JSX) | kerf-electronics |
| `.simulation` | FEA/simulation metadata | kerf-fem |
| `.bim` | Building information model elements | kerf-bim |
| `.family` | Part family with parameter variants | kerf-bim |
| `.schedule` | BOM/configuration schedule | kerf-bim |
| `.view` | Saved camera + visibility state | kerf-bim |
| `.sheet` | Layout sheet for drawings | kerf-bim |
| `.render` | Blender Cycles render scene | kerf-render |
| `.graph` | Signal/power graph connectivity | kerf-imports |
| `.subd` | Subdivision surface mesh | kerf-imports |
| `.mesh` | Raw triangulated mesh | kerf-imports |
| `.draft` | Sheet metal draft analysis | kerf-imports |
| `.tolerance` | GD&T tolerance schema | kerf-api |
| `.fem` | Finite element mesh + boundary conditions | kerf-fem |
| `.topo` | Topological optimization study | kerf-topo |
| `.cam` | CNC toolpath + operation list | kerf-cam |
| `.rf-study` | RF electromagnetic study | kerf-electronics |
| `.material` | Material definition with properties | kerf-api |
| `.equations` | Project-scoped parametric equations | kerf-api |
| `.canvas` | Freeform 2D annotation canvas | kerf-api |
| `.stair` | Staircase geometry + accessibility | kerf-bim |
| `.railing` | Railing/guardrail system | kerf-bim |
| `.curtain-wall` | Curtain wall panel system | kerf-bim |
| `.duct` / `.pipe` / `.conduit` | HVAC / piping / electrical routing | kerf-bim |
| `.step` / `.step-ref` | STEP B-rep import + pointer | kerf-cad-core + kerf-tess |

Also: `.assembly_lock`, `.script`, `.configurations` (tracked internally; no
dedicated LLM doc).

## Tool registry

Each plugin registers LLM tools into the **shared `ToolRegistry`** carried on
`PluginContext`:

```python
ctx.tools.register(
    name="feature_pad",
    spec=ToolSpec(name="feature_pad", description="…", parameters={…}),
    handler=run_feature_pad,
)
```

There are **~150 tools across 19 plugins**. `kerf-chat` reads the registry on
every request and ships the role-filtered list to the LLM. `write=True` tools
mutate project state; viewer role gets `read`-only filtering.

The LLM consults the per-plugin `llm_docs/` as a **doc-search corpus** before
touching non-`.jscad` files. The corpus is loaded at boot from every plugin
that ships one (kerf-imports, kerf-bim, kerf-electronics, kerf-render, kerf-chat).

## The AI loop

```
User chat → POST /api/projects/:pid/threads/:tid/messages
  1. Persist message; build LLM history
  2. Call LLM with tool registry (role-filtered: viewer = read-only)
  3. Persist assistant turn + any tool_calls
  4. No tool_calls? → done
  5. Execute every tool call inside the request handler
  6. Persist role=tool result rows; append to history
  7. Loop back to step 2; cap at 10 iterations
  8. Render affected files → push viewport update via SSE
```

Single HTTP request. A "make this 6 mm thick" can chain read → edit →
validate all visible as individual chat rows.

## Storage abstraction

`packages/kerf-core/src/kerf_core/storage/` defines a `StorageBackend` ABC;
concrete backends:

- **local** — disk under `./.kerf-storage`. Auth-protected
  `/api/blobs/{key}` serves bytes.
- **s3** — AWS SDK v2; works with S3, R2, MinIO. `download` returns a 302 to
  a presigned URL.
- **filesystem** — projects mirror to disk under `[storage].filesystem_root`
  as folders, so users can edit with their own tools.
- **git** — git mirror per-project; Kerf commits on every file write,
  branches per workspace variant. Stateless deploys use the `S3GitStorer`
  wrapper in `packages/kerf-cloud/`.

Selection is config-driven; the rest of the codebase only sees the interface.

## File revisions = undo

Every text edit appends a row to `file_revisions` with `source` of
`'user' | 'llm' | 'tool' | 'restore'`. The PATCH path, every write tool, and
restore actions all funnel through the same insert. `Cmd+Z` in the editor
calls the restore endpoint. Soft-deletes (`deleted_at` flag) keep revisions
readable so the History drawer can resurrect a deleted file.

Phase 4 made revision storage real-diff + SHA-256 deduped + safely prunable
(see [whats-new](./whats-new.md)); existing plaintext rows still read via the
legacy `content` column.

`[limits].file_revisions_max` (default 200) trims the oldest rows on each write.

## Two coexisting kernels

**JSCAD** — code → mesh in a Web Worker. Cheap, scriptable, great for
parametric exploration.

**.feature** — JSON feature tree backed by OCCT in WASM (browser) or
pythonOCC (server, via `kerf-cad-core`). Real B-rep features (fillets,
chamfers, shell, draft, holes), edge identity for selection-driven ops,
lossless STEP export.

Both kernels coexist per-file. Cross-kernel ops (Assembly combining `.jscad`
and `.feature` bodies) work at the mesh level — same trade Rhino and FreeCAD
make. This is intentional: code-first is unbeatable when the LLM is in the
loop; B-rep is unbeatable when you need precision and edge ops a mesh can't.

The planned [Sketch → JSCAD workflow](./plans/sketch-to-jscad.md) closes the
gap for users who want JSCAD's programmability with dimension-driven 2D input.

### Pure-Python geometry kernel (`kerf-cad-core/geom/`)

Sitting beneath the `.feature` pipeline is a pure-Python B-rep/NURBS kernel
in `packages/kerf-cad-core/src/kerf_cad_core/geom/`. It owns:

- **Validated B-rep topology** (`brep.py`): a full `Vertex → Edge → Coedge →
  Loop → Face → Shell → Solid → Body` hierarchy with per-entity tolerances.
  Every `Body` can be interrogated with `validate_body`, which enforces the
  generalised Euler–Poincaré formula (`V − E + F − H − 2(S − G) = 0`),
  2-manifold closure (each closed-shell edge used by exactly two coedges of
  opposite orientation), CCW/CW loop orientation relative to the oriented
  surface normal, tolerance monotonicity, and no dangling or duplicate
  coedges.
- **Euler operators** (`mvfs / mev / mef / kemr / kfmrh` + inverses): each
  mutates `(V, E, F, L, S, G)` by a delta that leaves the Euler–Poincaré
  residual at zero. `EulerError` is raised on misuse.
- **Analytic primitive surfaces**: `Plane`, `CylinderSurface`,
  `SphereSurface`, `TorusSurface`, `Line3`, `CircleArc3` — geometry adapters
  that satisfy the opaque curve/surface contract (`evaluate(t)` /
  `evaluate(u, v)` + `normal(u, v)`). NURBS curves and surfaces from
  `nurbs.py` satisfy the same contract directly.
- **Exact rational primitive B-reps** (`brep_build.py`): `box_to_body`,
  `cylinder_to_body`, `sphere_to_body`, `torus_to_body` — validated at
  construction time via `BuildError`.
- **Hardened SSI and closest-point** (`intersection.py`, `inversion.py`):
  surface–surface intersection via subdivision + Newton marching; curve and
  surface closest-point projection (`closest_point_curve`,
  `closest_point_surface`) used by fillets, offset surfaces, and trim.
- **Tolerant booleans** (`boolean.py`): `body_union` / `body_difference` /
  `body_intersection` on closed solid `Body` instances. The current
  implementation covers axis-aligned planar+planar, axis-aligned
  planar+cylindrical, and sphere+sphere combinations — general
  NURBS/NURBS imprint is roadmap follow-up. Every boolean result is
  asserted `validate_body`-clean before return.
- **G1/G2 fillets and blends** (`fillet_solid.py`): `fillet_solid_edge`
  replaces a B-rep edge with a rolling-ball fillet face (cylindrical for
  planar+planar, toroidal for planar+cylindrical) sewn back into a
  validated `Body`. Supported contracts: convex planar+planar and
  planar+cylindrical cap-rim edges; non-convex and general NURBS edges
  return `{"ok": False, "reason": "…"}` rather than emitting an invalid
  body.
- **Parametric feature DAG with persistent face IDs** (`history/dag.py`,
  `history/persistent_naming.py`): the `FeatureDAG` orchestrates
  incremental re-evaluation — `set_param` + `regenerate` re-evaluates
  only invalidated features in topological order. Persistent face/edge
  identity uses a `feature_id::role::fingerprint` scheme: roles are
  purely structural labels (e.g. `face:+X`, `face:cap_bottom`,
  `face:boundary:0`) that survive parameter edits. A downstream fillet
  referencing the top face of a box continues to resolve correctly after
  the box's height changes.

**What this is not**: the kernel is a robust foundation, not a complete
Parasolid replacement. Boolean inputs must currently satisfy the axis-aligned
analytic contract; chamfers are planar-face only; free-form NURBS/NURBS
booleans and general-edge fillets are roadmap items. The OCCT path (via
pythonOCC on the server or `occt-import-js` in the browser) remains the
route for arbitrary STEP geometry and advanced surface operations.

## Migrations

`packages/kerf-core/src/kerf_core/db/migrations/` holds SQL migration scripts
named `NNN_kind_*.sql`. The runner applies them in order. Each adds a new
value to the `files.kind` enumeration and/or alters the schema. The most
recent migrations cover `step_tess_input_spec` (047) and `revision_compaction`
(048).

## Cloud feature gate

Cloud-only plugins (`kerf-billing`, `kerf-cloud`) ship as separate packages
under `packages/`. They register only when included by the install persona
(`full`) or when `cloud_enabled=true` at runtime. The flag is read at server
startup.

## Single-binary deploy

`npm run build` runs `vite build` → static assets shipped alongside the Python
package. The CLI entry-point `kerf-server` (from `kerf-core`) boots everything:

```
kerf-server --config ./kerf.toml
```

Equivalent to `python -m kerf_core` or `uvicorn kerf_core.app:create_app`.

## Where to dive deeper

- **Capability tags + personas** — [capabilities.md](./capabilities.md).
- **API + data model** — this document, plus per-kind schemas in each
  plugin's `llm_docs/`.
- **LLM tool surface** — [llm-tools.md](./llm-tools.md).
- **Render pipeline** — [render-pipeline.md](./render-pipeline.md).
- **Cloud operator guide** — [cloud-operator.md](./cloud-operator.md).
- **Roadmap + philosophy** — [ROADMAP.md](../ROADMAP.md).

Next: [llm-tools.md](./llm-tools.md)
