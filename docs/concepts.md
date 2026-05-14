# Concepts

Kerf is a multi-domain CAD kernel where the **LLM is the primary author**. Every file is JSON,
every UI action is a tool call, and one project spans mechanical, electronics, architecture,
drafting, simulation, and scripting — with no separate apps or workbenches to switch between.

## The five nouns

```
Project
└── File           (.jscad, .feature, .sketch, .assembly, .bim, .circuit.tsx, ...)
    └── Object     (one entry in a file's export array)
                   └── Component  (an Assembly's instance of an Object at a transform)
```

Everything else — chat threads, revisions, members, share links — hangs off the Project.
Files cannot import across project boundaries; all geometry references stay within a project.

## 1. File kinds are first-class

Kerf supports **40+ file kinds**. Every domain is a JSON file kind with a schema doc
shipped inside the plugin that owns that kind (`packages/kerf-<plugin>/llm_docs/`).
The LLM reads the relevant schema doc before authoring or editing that kind — no
guessing, no hallucinated field names.

Key kinds:

| Kind | Extension | What it stores |
|------|-----------|----------------|
| `jscad` | `.jscad` | Code-driven mesh via `@jscad/modeling` in a Web Worker |
| `feature` | `.feature` | OCCT B-rep feature tree (pad/pocket/fillet/shell/draft…) |
| `sketch` | `.sketch` | 2D constraint geometry solved by planegcs |
| `assembly` | `.assembly` | Array of Components referencing Objects from other files |
| `drawing` | `.drawing` | Multi-sheet 2D manufacturing drawings with GD&T |
| `part` | `.part` | Library part with MPN, distributors, photos |
| `circuit` | `.circuit.tsx` | tscircuit electronics (JSX) |
| `bim` | `.bim` | Revit-style building model with hosted elements |
| `simulation` | `.simulation` | FEM/SPICE/RF/topology/CAM study metadata |
| `fem` | `.fem` | Finite element mesh + boundary conditions |
| `graph` | `.graph` | Grasshopper-style node-based DAG pipeline |
| `equations` | `.equations` | Project-scoped scalar parameters |
| `cam` | `.cam` | CNC toolpath + operation list |
| `step` | `.step` | Binary STEP B-rep import (read-only mirror) |

Binary files (STEP) keep a pointer in Postgres; bytes live in the configured Storage
backend (local disk, S3/R2/MinIO, or filesystem mirror). Every text file edit
appends a row to `file_revisions`, capped at 200 per file.

See [architecture.md](./architecture.md) for the full table.

## 2. LLM as primary author

The AI chat edits JSON via tool calls. Every UI action is also a tool call — the UI is a
**thin emitter** that translates user gestures into the same tool call interface the LLM uses.
One `make this 6 mm thicker` chains read → edit → validate as individual chat rows visible in
the thread.

Each plugin registers its own LLM tools into the shared `ToolRegistry` carried on
`PluginContext`. The full surface across 19 plugins is **~150 tools**. The LLM sees
a role-filtered list: viewer role gets read-only tools only. Write tools mutate
project state.

Before touching any non-`.jscad` file, the LLM queries `search_kerf_docs` → reads
the matching `packages/kerf-<plugin>/llm_docs/<topic>.md` → makes an informed tool
call. This doc-search loop is the reason the LLM can productively edit `.feature`,
`.bim`, `.circuit`, and all the other domain-specific kinds without hallucinating
schemas.

See [llm-tools.md](./llm-tools.md) for the full tool surface.

## 3. Two kernels in one project

**JSCAD** — evaluates `.jscad` code in a Web Worker. Triangulated mesh output. Cheap,
scriptable, great for parametric exploration. The LLM can freely generate and mutate it.
IndexedDB caches meshes keyed by JSCAD content hash so repeated evals are instant.

**.feature** — JSON feature tree evaluated by OCCT (WASM in the browser, pythonOCC
via `kerf-cad-core` on the server). Real B-rep: fillets, chamfers, shell, draft,
holes, ribs, helical threads. Edge identity is preserved for selection-driven ops.
Lossless STEP export. No code — just a declarative list of ordered operations.

Both kernels coexist per-file. Assemblies compose both at the mesh level — same trade
Rhino and FreeCAD make. This is intentional: code-first is unbeatable when the LLM is in
the loop; B-rep is unbeatable when you need precision and edge ops a mesh can't give you.

See `packages/kerf-chat/llm_docs/feature.md` and `packages/kerf-chat/llm_docs/jscad.md`.

## 4. File revisions are diff-compressed

Every text edit appends a row to `file_revisions` with `source` of `'user' | 'llm' | 'tool' | 'restore'`.
Phase 4 (May 2026) reworked storage as a content-hashed delta chain — revisions share
SHA-256-addressed blobs. Real diffs + dedup gave ~82× size reduction on a representative
project corpus compared to storing full copies, plus a safe-pruning path.

Every save is a checkpoint; `Cmd+Z` (Editor → Restore) calls the restore endpoint which
replays the revision chain backwards. Soft-deletes keep history readable so the History
drawer can resurrect a deleted file. The `[limits].file_revisions_max` (default 200) trims
the oldest rows on each write.

See `packages/kerf-imports/llm_docs/sheet_revisions.md` for the drawing-side revision flow.

## 5. Library Parts and Assemblies share the same nouns

- **Part** = an entire file (`.jscad`, `.feature`, `.step`…). It exports an array of Objects.
  Think OnShape "part studio" — one source file produces a family of related solids,
  each independently selectable in the viewport or in an Assembly.
- **Object** = one entry in that array: `{ id, geom }` where `geom` is the geometry handle
  used everywhere (clicked in the viewport, dropped as a chip in chat, referenced from
  assemblies, imported by other files).
- **Component** = an Assembly's instance of an Object at a 4×4 transform.

```ts
// Assembly Component
{ id: 'left-bracket', file_id: '...', object_id: 'wall', transform: [...16 nums] }
```

The same Object can be placed multiple times (different `id`, different transform) —
that's how repeated parts (screws, clips, grommets) work. A `.part` file adds
MPN/distributor data on top of this structure for library management.

See `packages/kerf-chat/llm_docs/part.md` and
`packages/kerf-chat/llm_docs/assembly.md`.

## 6. Doc-search loop

Before touching any file kind, the LLM queries `search_kerf_docs` → reads matching
`packages/kerf-<plugin>/llm_docs/<topic>.md` → makes an informed tool call. The corpus covers:

- Every file kind schema (40+ docs spread across kerf-chat, kerf-imports, kerf-bim,
  kerf-electronics, kerf-render)
- MEP routing vocabulary (`packages/kerf-bim/llm_docs/mep.md`)
- PCB layer stack and DRC rules (`packages/kerf-chat/llm_docs/pcb_layers.md`,
  `packages/kerf-chat/llm_docs/pcb_drc.md`)
- Feature-tree semantics and multi-transform patterns (`packages/kerf-chat/llm_docs/feature.md`)
- Simulation configs and solvers (kerf-fem, kerf-topo, kerf-cam, kerf-electronics)
- BIM categories and hosted relationships (`packages/kerf-bim/llm_docs/bim.md`,
  `packages/kerf-bim/llm_docs/bim_categories.md`)

The loop: **user chat → LLM queries docs → reads schema → tool call → execute → render → SSE push to viewport**.

## 7. OSS vs Cloud — same codebase

Cloud-only functionality ships as two proprietary plugin packages
(`packages/kerf-billing/`, `packages/kerf-cloud/`). They install only when the
`full` persona is selected. The `cloud_enabled` flag gates registration at
runtime — when off, the packages load but advertise an empty `provides=[]`
list (dormant).

| Capability                                  | Plugin       |
|---------------------------------------------|--------------|
| Paystack billing (USD→ZAR daily FX, ZAR settlement) | kerf-billing |
| Email (Resend/SES/SMTP)                     | kerf-cloud   |
| S3 Git Storer (stateless bare-repo deploys) | kerf-cloud   |
| Distributor live pricing sweep              | kerf-cloud   |
| GitHub OAuth (AES-GCM encrypted tokens)     | kerf-cloud   |
| Workshop sharing + library submissions      | kerf-cloud   |
| STEP pre-tessellation (server-side glTF)    | kerf-tess (OSS, just needs pythonOCC) |
| Everything else                             | OSS plugins  |

`local_mode` is forced off when `cloud_enabled=true`. Pluggable storage
(local / S3/R2/MinIO / filesystem mirror / git mirror per-project).

See [cloud.md](./cloud.md) and [capabilities.md](./capabilities.md).

## 8. Parametric stack — three layers

Kerf has three distinct parametric layers, each with a different scope:

| Layer | File | What it does |
|-------|------|--------------|
| Scalar params | `.equations` | Project-wide numeric variables; evaluated via mathjs; feed into features and graphs |
| Feature placeholders | `.feature` | `${name}` placeholders resolve to equation values at eval time |
| Node DAG | `.graph` | Grasshopper-style pipeline; nodes drive feature ops via `@nX.out` references |

`.equations` and `.feature` compose: equations feed feature placeholders. `.graph` is the
highest-level layer — it can invoke feature ops as nodes.

```
.equations  →  .feature  →  .graph
     ↑               ↑
     └── configs override equations scope per-variant
```

Configurations (M3/M4/M5, long/short, engraved/blank) produce multiple flavors from a
single source file by merging config params *over* the equations scope at eval time.

See [parametric.md](./parametric.md), `packages/kerf-chat/llm_docs/equations.md`,
`packages/kerf-chat/llm_docs/feature.md`, and `packages/kerf-imports/llm_docs/graph.md`.

## 9. Categories + hosted refs in .bim

The `.bim` kind implements a **Revit-style data model** for architecture:

- **Categories** (walls, doors, windows, floors, ceilings, stairs, railings, curtain walls,
  MEP ducts/pipes/conduits) own **Element Types**
- **Elements** are instances of types, placed at a location with a level and a transform
- **Hosted elements** (doors in walls, windows in walls, fixtures on walls, electrical
  fixtures on ceilings) reference their host via `host_id`
- **Spatial hierarchy**: Site → Building → Level → Zone

```
Category: Walls
  └── Element Type: "Exterior Wall 200mm"
        └── Element: Wall #1 (host_id: null, level: Level 1)
              └── Element: Door #1 (host_id: wall-1)
                    └── Element: Door Hardware #1 (host_id: door-1)
```

Geometry is either `.jscad` mesh or `.feature` B-rep. BIM elements point to the geometry
file via `geometry_file_id` and `object_id`. MEP elements additionally carry routing
connectivity (duct/pipe segments connect at junctions).

See `packages/kerf-bim/llm_docs/bim.md` and
`packages/kerf-bim/llm_docs/bim_categories.md`.

## 10. Domain-specific simulations — server-side in compute plugins

Heavy CPU/GPU compute runs inside the relevant plugin (kerf-fem, kerf-cam,
kerf-topo, kerf-electronics, kerf-render). The `kerf-workers` plugin
(`workers.harness`) manages long-running jobs out of the request thread. The
LLM triggers runs and reads results via tool calls.

| Domain                 | Kinds                  | Plugin            |
|------------------------|------------------------|-------------------|
| Structural FEM         | `.fem`, `.simulation`  | kerf-fem          |
| SPICE circuit          | `.circuit.tsx`         | kerf-electronics  |
| RF / electromagnetic   | `.rf-study`            | kerf-electronics  |
| Topology optimization  | `.topo`                | kerf-topo         |
| CAM                    | `.cam`                 | kerf-cam          |
| Sheet metal            | `.draft`               | kerf-imports      |
| STEP tessellation      | `.step` → glTF         | kerf-tess         |
| Rendering              | `.render` → image      | kerf-render       |

All results are JSON blobs stored in Postgres + object storage. The LLM can query
job status, retrieve results, and trigger new runs. STEP files ≥5 MB are stored
as `kind='step-ref'` with a SHA-256 content pointer to avoid duplicating large
binaries.

See the per-plugin `llm_docs/` (e.g. `packages/kerf-fem/llm_docs/`,
`packages/kerf-cam/llm_docs/`).

## Quick reference — schema docs by domain

| Domain              | Start here                                                |
|---------------------|-----------------------------------------------------------|
| Mechanical / JSCAD  | `packages/kerf-chat/llm_docs/jscad.md` · `feature.md`     |
| Sketching           | `packages/kerf-chat/llm_docs/sketch.md`                   |
| Assemblies          | `packages/kerf-chat/llm_docs/assembly.md`                 |
| Drawings            | `packages/kerf-chat/llm_docs/drawing.md`                  |
| Architecture / BIM  | `packages/kerf-bim/llm_docs/bim.md` · `bim_categories.md` |
| Electronics         | `packages/kerf-chat/llm_docs/circuit.md` · `pcb_layers.md` |
| Parametric          | `packages/kerf-chat/llm_docs/equations.md` · `packages/kerf-imports/llm_docs/graph.md` |
| FEM                 | `packages/kerf-fem/llm_docs/fem.md`                       |
| CAM                 | `packages/kerf-cam/llm_docs/cam.md`                       |
| Surfacing / STEP    | `packages/kerf-cad-core/` source comments                 |

---

Next: [sketching.md](./sketching.md) · [assemblies.md](./assemblies.md) · [parametric.md](./parametric.md) · [electronics.md](./electronics.md) · [architecture.md](./architecture.md)
