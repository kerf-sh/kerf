# Kerf — Roadmap

This is the public roadmap for Kerf, an open-source chat-driven CAD tool. It
captures shipped capabilities, in-flight work, and the bigger phases ahead.
The data-model + API spec lives in [CONTRACT.md](./CONTRACT.md); this
document is about *direction*, not interface details.

Kerf is dual-licensed: the OSS core (everything outside `cloud/`,
`backend/cloud/`, and `src/cloud/`) is MIT. The hosted-tier code under those
paths is governed by [cloud/LICENSE](./cloud/LICENSE).

---

## Vision

A chat-driven CAD tool that produces real engineering output. Code-first
(JSCAD) for parametric work, visual sketcher with constraints for 2D, real
B-rep features (OpenCascade) for solid modeling parity with FreeCAD/SolidWorks,
TechDraw-style 2D drawings for documentation. Browser-native, single-binary
local install, optional hosted tier with billing + workshop sharing + git.

---

## Status overview

| Area | Status | Notes |
|---|---|---|
| **Auth + projects + files + chat (CRUD)** | ✅ shipped | Postgres-backed, JWT, Google OAuth |
| **JSCAD authoring loop** | ✅ shipped | Worker-based eval, IndexedDB mesh cache, file-revisions undo, 4-tier debounce |
| **2D parametric sketcher (planegcs)** | ✅ shipped | Constraints (parallel, equal, perpendicular, distance, angle, tangent), drag-to-solve, color-coded DOF state |
| **Assembly model (Object/Part/Component)** | ✅ shipped | Insert dialog with checkboxes, Copy/Delete-Object via revisions |
| **2D technical drawings (TechDraw-flavored)** | ✅ shipped | Multi-sheet, dimensions (distance/radius/diameter/angular/baseline/chain/ordinate), section hatching, leaders/balloons, GD&T frames, centerlines, break-lines |
| **Cloud: Workshop sharing** | ✅ shipped | Free-sharing gallery, like + fork, OnShape-style insert dialog |
| **Cloud: Paystack billing** | ✅ shipped | USD pricing, ZAR settlement, FX refresh, webhook-credited prepaid balance |
| **Cloud: Git (commits + branches + merge + GitHub sync)** | ✅ shipped | go-git, multi-lane lattice graph view, GitHub OAuth, AES-GCM-encrypted tokens |
| **Filesystem storage backend** | ✅ shipped | Projects mirror to disk as folders for local-install workflows |
| **Single-binary build with embedded frontend** | ✅ shipped | `npm run build` → ~32 MB self-contained `kerf` |
| **Brew formula + curl install** | ✅ shipped | Homebrew tap + `install.sh` |
| **Test runner (OSS + cloud, separate)** | ✅ shipped | 4 OSS scenarios, 4 cloud scenarios, surfaces real bugs |
| **Drawing snap + projection visibility** | 🚧 in flight | Endpoint/midpoint/center/intersection snap, fix view-rendering bug |
| **Feature panel: Pad / Pocket / Revolve** | 🚧 in flight | JSCAD codegen layer; FreeCAD-style modal flow |
| **Cloud git → object-storage Storer** | 🚧 in flight | Stateless serverless deploys (R2/S3 backed bare repos) |
| **Test scenarios: assembly + sketcher + drawing** | 📋 next | Integration coverage |
| **Sketcher v2 improvements** | 📋 next | Trim/extend/fillet (2D), mirror/pattern, ellipse/B-spline, more constraints, external geometry, 3D backdrop, multi-loop holes |
| **Equations / global parameters** | 📋 next | Project-level `.equations` JSON; mathjs expressions; injected into JSCAD + `.feature` + `.sketch` eval; LLM-flattering parametric layer; no kernel dependency |
| **Configurations / variants** | 📋 next | Per-file parameter overrides (M3/M4/M5 size flavors of one Part); editor config dropdown; assembly Components reference specific config; BOM groups by `(file, config)` |
| **Materials database (`.material` Library kind)** | 🔮 planned | Curated `kerf-system/materials` Library project; ~500 common engineering materials (E/ν/ρ/α/yield/k/cₚ); consumed by FEM, tolerance, Part defaults, drawing callouts; shared mech ↔ architecture |
| **3D assembly mates (Tier 0 foundation)** | 🔮 planned | Coincident / concentric / parallel / perpendicular / distance / angle / tangent; SolveSpace solver (GPL3) subprocess; `mates: [...]` on `.assembly`; depends on Phase 3 |
| **Scripting: `.script.ts` automation** | 🔮 planned | Browser-Worker TypeScript via esbuild-wasm; typed `kerf.*` API; backend heavy ops (FEM/CAM/STEP-tess) called via fixed RPC; never evals user code on the backend |
| **`.feature` file kind + OCCT integration (Phase 2)** | 🔮 planned | Real B-rep features: Fillet/Chamfer/Shell/Draft/Hole alongside the JSCAD path |
| **Edge/face selection + direct modeling (Phase 3)** | 🔮 planned | Pick edges/faces in viewport, run features against them |
| **FEM: mechanical analysis** | 🔮 planned | CalculiX + Gmsh subprocess; `.fem` file kind; F1 = linear static + modal + bonded contact; local + cloud workers; depends on Phase 3 |
| **Tolerance stack-up** | 🔮 planned | 1D worst-case + RSS between two faces; walks dimension chain through mates; Monte-Carlo follow-on; depends on 3D mates |
| **CAM toolpath generation** | 🔮 planned | OpenCAMlib (LGPL 2.1); 2.5D ops (face/contour/pocket/drill/profile); G-code with selectable post (LinuxCNC/GRBL/Mach3/Fanuc); `.cam` file kind; depends on Phase 2 |
| **Topology optimization** | 🔮 planned | CalculiX SIMP wrapper; density-field → mesh; `.topo` file kind references `.feature` design space; "make it 30% lighter" demo; depends on FEM |
| **Architecture: IFC + text-DSL** | 🔮 planned | Architectural project type. `.bim` text-DSL → IfcOpenShell (LGPL) compiler → `.ifc` artifact → web-ifc/Three.js viewer. Walls/slabs/spaces/openings/levels/site; IFC4 subset grows iteratively |
| **NURBS surfacing (Phase 4)** | 🔮 planned | sweep1/sweep2/networkSrf/blendSrf, surface continuity. Rhino-tier territory. |
| **Auth-optional removal** | 📋 next | Replace with auto-account-on-first-run |
| **Performance: server-side STEP pre-tessellation** | 📋 next | wazero or Node sidecar; reduces in-browser STEP parse |
| **Performance: diff-based + compressed revisions** | 📋 next | ~50× shrink on `file_revisions` storage |
| **Project-type enum (mechanical / electronics / architecture …)** | 🔮 planned | Mandatory at create; gates renderer, LLM tools, file extensions; workshop multi-type from day one |
| **Electronics projects via tscircuit** | 🔮 planned | TSX → Circuit JSON; schematic + PCB + 3D-board viewers; LLM edits `.circuit.tsx` |
| **Cross-project parts (PCB-as-part in mechanical assembly)** | 🔮 planned | Reference electronics project's `board_3d` or `board_outline_2d` from a mechanical Component, pinned or tracking-latest |
| **Library system v1 (Parts + BOM)** | 🚧 in flight | `kind='part'` files with rich metadata; Assembly Components reference Parts; BOM rollup endpoint + CSV export; per-Part `visibility` (private/unlisted/public); product photos attached to Parts; "verified publisher" flag for curated libraries (Adafruit, Sparkfun, McMaster, Misumi, etc.). KiCad-style for both mech and electronics. |
| **Library Phase 2: distributor APIs** | 🔮 planned | Live pricing + stock from DigiKey / Mouser / LCSC / McMaster |
| **Library Phase 3: curated manufacturer libraries** | 🔮 planned | Verified-publisher accounts (e.g. `kerf-system/adafruit-parts`), Workshop badge, manufacturer-contributed updates via PR |
| **Library as its own top-level area (split from Workshop)** | 📋 next | New `/library` route: parts catalog (search, category, verified badge). `LibraryPicker` modal replaces AssemblyEditor's add-component dropdown. New `/api/library/parts` canonical endpoint, `/api/workshop/parts` kept as deprecated alias. Workshop stays project-showcase-only. Sharing model mirrors Workshop: per-Part `visibility='public'` gates inclusion, verified publishers float to top. |
| **BOM UX rework** | 📋 next | Inline collapsible BOM panel inside AssemblyEditor (today it lives at a separate `/bom` route, divorced from the model). Add quantity overrides, non-stocked flags, per-row notes; surface MOQ / lead-time / alternates from distributor data. |
| **Electronics objects/features fix** | 📋 next | CircuitEditor today shows the same left-bottom ObjectsPanel as JSCAD/Feature files, which doesn't match the domain. Replace with a circuit-specific Components/Nets panel parsed from the compiled CircuitJSON. `cad_component` references resolve to real Library parts (instead of box approximations) for the 3D tab. Bidirectional link Library ↔ Circuit. |
| **LLM tool consolidation (doc-search + small fixed surface)** | ✅ shipped | ~30 domain-specific tools collapsed into a small fixed surface (file ops, object ops, BOM, validation, four `create_*` scaffolders) plus `search_kerf_docs` over an embedded markdown corpus at `backend/internal/llm/docs/`. The model reads the relevant `/docs/llm/<topic>.md` page and edits the file's JSON / TSX directly via `write_file` / `edit_file`. Adding a new domain is a markdown change, not a Go change. |
| **Chat panel collapsible** | ✅ shipped | Topbar `PanelRightClose/Open` button toggles the entire 380px column away — center main expands. State persisted to `localStorage`. |
| **User avatars + CDN-backed images** | 📋 next | `users.avatar_storage_key` column. Multipart upload endpoint + Google-OAuth-triggered avatar pull. Storage abstraction gains `CDNBaseURL` so cloud serves through bunny.net Pull Zone, locally serves through `/api/blobs/`. |
| **Workspaces (orgs) — multi-member containers** | 📋 next | New `workspaces` table (slug, name, avatar) + `workspace_members` (role: owner/admin/member). Projects gain `workspace_id`; migration creates a personal default workspace per existing user and re-parents their projects. Routes scoped under `/w/:slug/`. **OSS scope:** workspace CRUD, member invite (email if email-provider configured else copy-link), role-based access on projects, settings page (rename, slug change, avatar upload). **Cloud-only:** billing attaches to workspace (not user); each workspace gets its own credit balance, invoices, plan. The internal `useWorkspace` zustand store needs renaming to avoid the term collision — propose `useEditor` or `useEditorState`. |
| **Project change timeline (with avatars)** | 📋 planned | `/api/projects/:pid/activity` merges file_revisions + chat_messages + project mutations. ActivityTimeline component with avatar pills. Tab or slide-out from the editor. Depends on avatars landing first. |
| **Docs: ROADMAP + restructured /docs + landing revamp** | 🚧 in flight | This document is the start |

Legend: ✅ shipped · 🚧 in flight · 📋 next · 🔮 planned (multi-quarter)

---

## Modeling philosophy: two coexisting paradigms

Kerf supports **two kernels in one project**, picked per-file:

```
.jscad      → JSCAD code → mesh                (cheap, scriptable, ~one sprint to ship features)
.feature    → feature tree → OCCT BRep → mesh  (precise, exports STEP losslessly, real fillets)
.sketch     → planegcs Geom2 profile           (consumed by either)
.assembly   → Components ref any 3D file kind  (kernel-agnostic)
.drawing    → projects views from any 3D       (kernel-agnostic)
```

A project can mix both styles. Operations *within* a `.feature` file run at
full B-rep fidelity; operations *across* `.feature` and `.jscad` files
(assemblies, CSG mixes) work at mesh level — same trade Rhino/FreeCAD make.

Why both? Code-first is unbeatable for parametric exploration with the
chat-LLM in the loop; B-rep is unbeatable for engineering-precision output and
features the mesh world can't deliver (precise fillets, lossless STEP export,
edge identity for selection-based ops).

---

## Parametric foundation: equations + configurations

Both can ship in parallel with Phase 2/3 — no kernel dependency. They
are the layer that turns kerf from "a tool that draws shapes" into "a
tool that captures parametric intent." Outsized leverage for the LLM:
a model that can edit a JSON parameter table fluently is a model that
can drive parametric exploration in chat.

### Equations: project-level named parameters

New file kind `.equations` — JSON map of named values:

```
{
  "wheel_diameter": { "value": 120, "unit": "mm", "description": "outer rim" },
  "wheel_radius":   { "expression": "wheel_diameter / 2", "unit": "mm" },
  "spoke_count":    { "expression": "ceil(wheel_diameter / 20)", "unit": "scalar" }
}
```

- **Expression eval:** [mathjs](https://mathjs.org/) (MIT). Numeric only — no symbolic CAS.
- **Resolution:** topological sort by dependency, cycle detection, evaluate.
- **Injection:** the resolved `params` object reaches every file eval.
  JSCAD worker exposes it on the eval scope (`params.wheel_diameter`).
  `.feature` JSON values can be either literals or expression strings
  (`"wheel_diameter / 4"`). `.sketch` constraint dimensions can
  reference parameter names.
- **Units:** declared per parameter; surfaces in drawing dimensions
  ("Ø120mm"). Optional in v1 — default scalar/length-mm.
- **LLM tool:** `set_parameter({ name, value | expression, unit?, description? })`.
  Model can also `edit_file` the `.equations` JSON directly. Doc page at
  `backend/internal/llm/docs/equations.md`.

### Configurations: per-file variants

Schema, on any file that opts in:

```
configurations: {
  active: "M4",
  configs: {
    "M3": { diameter: 3, thread_pitch: 0.5, head_diameter: 5.5 },
    "M4": { diameter: 4, thread_pitch: 0.7, head_diameter: 7   },
    "M5": { diameter: 5, thread_pitch: 0.8, head_diameter: 8.5 },
    "M6": { diameter: 6, thread_pitch: 1.0, head_diameter: 10  }
  }
}
```

- **Eval pipeline:** `defaults → project equations → active config overrides → file body uses final values`.
  Configs are just an override layer on top of the same expression evaluator equations use.
- **Editor:** config dropdown at the top of any file with configurations.
  Switching re-evals viewport and any open drawings.
- **Assembly references:** Component rows gain a `config` field — "this
  instance uses the M4 config". BOM rollup groups by `(file_id,
  config_id)` so 4×M3 + 2×M4 bolts show as two BOM lines.
- **Insert dialog:** picking a Part exposes its configuration list;
  default is the file's `active`.
- **Library impact:** Parts surface their config list in the Library
  picker — "M-series cap screw" shows as one Part with M3/M4/M5/M6
  configs, not four separate Parts. This was always the right shape
  for libraries; it only becomes possible once configurations exist.
- **LLM tools:** `add_configuration({ file, name, overrides })`,
  `set_active_configuration({ file, name })`. Doc page at
  `backend/internal/llm/docs/configurations.md`.

### Phasing

- **E1.** `.equations` file kind, mathjs expression eval, project-level
  params injected into JSCAD + `.feature` eval, sketch dimensions can
  reference parameter names. (Equations alone — no configs yet.)
- **C1.** Per-file configurations (parameter overrides), editor
  dropdown, assembly Component config selection, BOM groups by `(file, config)`,
  Library Parts expose configs in the picker.
- **E2 / C2.** Drawing dimensions display parameter names alongside
  values ("width = 100mm"). Insert-dialog config preview thumbnails.
- **E3 / C3.** Cross-project parameter inheritance — a master assembly
  project defines parameters, sub-projects pull from it. Depends on
  cross-project Component refs landing first.

### Non-goals

- **Symbolic math / CAS.** mathjs is numeric; that's enough.
- **Parameter optimization** ("find values that minimize this
  objective"). Tier 1 advanced capability later.
- **Config-specific feature suppression** ("delete this fillet for the
  M3 config but keep it for M4"). Error-prone even in SolidWorks; punt.
- **Auto-generated config tables** ("create M3 through M30 stepping by
  1"). Punt to the scripting layer.

---

## Scripting: `.script.ts` automation + safe backend RPC

The FreeCAD-Python equivalent — user-written code that drives the
project — reimagined to fit kerf's actual constraints (browser
runtime, multi-tenant cloud, LLM in the loop). It's also a force
multiplier *for* the LLM: the model can write a one-shot script when
no fixed tool exists for the job, run it, see the result, and discard
it.

### Language: TypeScript

Runtime is **TypeScript executed in a Web Worker via esbuild-wasm**.
Reasons:

- Same V8 runtime as JSCAD — zero impedance mismatch with existing files.
- LLM is exceptional at TypeScript and benefits from the type system.
  The kerf API ships as a `.d.ts` and lands in the editor's IntelliSense
  AND in the model's context.
- ~10× faster than Pyodide for typical CAD math; ~5× smaller bundle
  (esbuild-wasm ≈ 2 MB vs Pyodide ≈ 10 MB).
- Instant startup (~50 ms) vs Pyodide's 1-3 s first eval.

The script runtime is abstracted so **Pyodide can drop in later** as a
second language frontend (same `kerf.*` API, different language) if
Python demand materializes. Not v1.

### Architecture: safe heavy-lifting via fixed RPC

The hard rule: **never execute user code on the backend.** Only fixed,
audited Go-implemented operations ever run server-side. User scripts
live entirely in the browser Worker; when they need heavy compute,
they call a typed RPC into the backend.

```
┌─ Browser ───────────────────────────────┐    ┌─ Backend ──────────┐
│  Editor (.script.ts source)             │    │                    │
│       │  esbuild-wasm                   │    │                    │
│       ▼                                 │    │                    │
│  Web Worker (compiled JS)               │    │                    │
│       │ uses kerf.*                     │    │                    │
│       │                                 │    │                    │
│  ├─ kerf.files.read()        in-process │    │                    │
│  ├─ kerf.equations.set()  ──────────────┼───►│ go handler         │
│  ├─ kerf.fem.run()        ──────────────┼───►│ go handler ──► ccx │
│  └─ kerf.cam.toolpath()   ──────────────┼───►│ go handler ──► cam │
└─────────────────────────────────────────┘    └────────────────────┘
```

The backend exposes the *same* registry the LLM tool surface already
uses — one source of truth, two callers (LLM + user TS scripts).
Adding a new heavy op makes it usable from both surfaces at once. No
new attack surface, no eval, no sandbox infrastructure to operate.

### File kind: `.script.ts`

```
project/
  ├── parts/wheel.feature
  ├── assemblies/main.assembly
  ├── parameters.equations
  └── scripts/
        ├── regen-all-steps.script.ts
        ├── batch-rename-parts.script.ts
        └── validate-bom.script.ts
```

A script imports a typed `kerf` global:

```ts
import { kerf } from "@kerf/api";

for (const wheel_d of [80, 100, 120, 140]) {
  await kerf.equations.set("wheel_diameter", wheel_d);
  const result = await kerf.fem.run({
    source_file: "parts/wheel.feature",
    materials: [{ id: "AL-6061", E: 69e9, nu: 0.33, rho: 2700 }],
    fixtures: [{ face_ref: "hub_inner", type: "fixed" }],
    loads:    [{ face_ref: "rim", type: "pressure", magnitude: 1e5 }],
    studies:  ["static"],
  });
  console.log(`d=${wheel_d} → max von Mises = ${result.max_von_mises} Pa`);
}
```

Editor surface: a "Run" button compiles and executes; a console panel
streams `console.log` output and RPC progress; runtime errors land in
the panel with source-mapped stack traces.

### `kerf.*` API surface (initial)

**Read:**
- `kerf.files.list()`, `kerf.files.read(path)`, `kerf.files.history(path)`
- `kerf.equations.read()`, `kerf.equations.get(name)`
- `kerf.assemblies.read(path)`, `kerf.bom.compute(assemblyPath)`
- `kerf.config.list(filePath)`, `kerf.config.get(filePath, name)`

**Mutate** (every mutation routes through `file_revisions`, so undo /
branch / git-sync work the same as for human edits):
- `kerf.files.write(path, content)`, `kerf.files.delete(path)`
- `kerf.equations.set(name, valueOrExpr)`, `kerf.equations.delete(name)`
- `kerf.config.set(filePath, name, overrides)`, `kerf.config.activate(filePath, name)`
- `kerf.feature.run(filePath, op, params)`

**Heavy (RPC, polled, awaited):**
- `kerf.fem.run({...})` → resolves with summary + result-file ID
- `kerf.cam.toolpath({...})` → same pattern (lights up when CAM lands)
- `kerf.step.tessellate({...})` → same pattern (lights up with the perf phase)

Each `kerf.*` call has a 1:1 entry in the backend RPC registry; the
same registry powers the LLM tool surface.

### Phasing

- **S1.** `.script.ts` file kind, esbuild-wasm in-browser compile, Web
  Worker runtime, **read-only** `kerf` API, `console.log` panel,
  source-mapped errors.
- **S2.** Mutation API (`writeFile`, `setParameter`,
  `setConfiguration`, `runFeature`). Mutations flow through
  `file_revisions` so undo / branches / git-sync work uniformly.
- **S3.** Heavy-op RPC (`kerf.fem.run`, `kerf.cam.toolpath`,
  `kerf.step.tessellate`). The polling/await wrapper is shared
  infrastructure; new heavy ops register a backend handler + a thin
  client method.
- **S4.** Long-running script lifecycle: progress reporting,
  structured cancellation, run history, scheduled runs (cron) on the
  cloud tier.
- **S5.** Optional Pyodide runtime as a second language frontend,
  same `kerf.*` API. Only with real demand.

### Dependencies

- **Equations + configurations land first** — scripts typically read
  parameters and write configs; the API is shaped by them.
- **Heavy-op RPCs follow their backend feature** — `kerf.fem.run`
  lights up when FEM workers exist, `kerf.cam.toolpath` when CAM
  exists, etc. S3 is incremental, not a single ship.
- **Phase 2 (`.feature`) is independent** — TS scripts don't need
  B-rep, but become more useful once `.feature` lands because the
  feature ops become scriptable.

### Non-goals

- **Backend execution of user code.** Never. Even sandboxed. The cost
  of operating that infrastructure dwarfs its value when fixed RPC
  covers the heavy-lift case.
- **Plugin marketplace.** Scripts are per-project files,
  version-controlled with the project. No global install or app-store.
- **Multi-language v1.** TypeScript only; Pyodide is S5-or-later.
- **Direct shell / filesystem / network from scripts.** The `kerf.*`
  API is the only outside surface; the browser Worker enforces this.
- **Custom feature types via scripting.** Tempting but couples
  scripting to the kernel; punt to a separate "user feature" plan.

---

## Phase 2: `.feature` files + OCCT integration

The next big swing. Detailed plan:

### Scope
- New file kind `feature`. JSON-encoded feature tree on disk; OCCT BRep at runtime.
- WASM worker bundling [opencascade.js](https://github.com/donalffons/opencascade.js) (~7-15 MB, lazy-loaded).
- Initial feature set: Pad, Pocket, Revolve, Loft, Sweep, Fillet, Chamfer, Shell, Draft, Hole.
- Tessellation pipeline: BRep → triangulated mesh for renderer; preserves face/edge IDs for selection.
- LLM tools: `feature_pad`, `feature_pocket`, `feature_fillet`, etc. — each a structured edit on the feature tree.
- STEP/IGES export at B-rep precision (replaces the current mesh-export STEP).
- `.feature` files render in the same Editor as `.jscad`, but the chat tools, Object panel, and feature panel switch behavior based on the file kind.

### Open questions
- Feature tree representation: array of {op, params, refs} vs. linked list with explicit dependency edges. Likely the simpler array.
- Edge/face references inside the tree: persistent across edits is *the* hard problem. OCCT's `BRepTools::Substitution` + naming heuristics. We'll start with simple sha-based IDs and iterate.
- Mesh ↔ BRep bridge for cross-kernel ops in assemblies.

### Non-goals (Phase 2)
- Direct modeling (push/pull). That's Phase 3.
- NURBS surfacing tools beyond what OCCT exposes for free. Phase 4.
- Real-time multi-user editing. Different project entirely.

---

## Phase 3: Direct modeling + viewport selection

After `.feature` lands and stabilizes:
- Click an edge/face in the 3D viewport → it becomes a reference.
- "Push/pull this face" — direct-edit moves on top of the feature tree.
- Sketch on a face (place the sketch's plane on a real face of an existing body).
- Pattern features (linear, polar, mirror).

---

## FEM: mechanical analysis (post-Phase 3)

Finite element analysis as a first-class mechanical capability.
Chat-driven "make this part, run FEM, report the factor of safety" is
the demo that justifies a chat-LLM CAD tool over traditional GUIs.

### Stack

- **Solver: CalculiX** (GPL2, subprocess) — most capable OSS mechanical
  solver; Abaqus-compatible `.inp` syntax, which is the single most
  LLM-trainable FEM format in existence.
- **Mesher: Gmsh** (GPL2, subprocess) — de facto OSS mesher.
- **License posture:** subprocess invocation only; never linked into
  the MIT kerf binary. Runtime subprocess use of GPL software is not
  derivative work. Both tools install separately (`brew install --cask
  kerf-fem-tools` locally; baked into the cloud VM image).

### Data model

New file kind `.fem` — JSON study spec referencing a 3D source file
the way `.drawing` already does:

```
.fem → {
  source_file_id, source_revision_id?,
  mesh:      { size, type: "tet" | "hex_dominant" },
  materials: [{ id, E, nu, rho, ... }],
  fixtures:  [{ face_ref, type: "fixed" | "slider" | "pinned" }],
  loads:     [{ face_ref, type: "force" | "pressure" | "torque", magnitude, direction }],
  studies:   ["static", "modal", ...],
  solver_opts
}
```

Results are derived artifacts keyed by `(source_revision_id,
fem_revision_id)` — same caching pattern as the planned STEP
pre-tessellation cache. Stored: deformed mesh, per-element stress
tensor, modal frequencies + mode shapes, summary JSON (max stress, FoS).

### F1 scope (first ship)

- **Linear static** — forces, pressures, fixed/sliding/pinned faces,
  isotropic materials. Output: von Mises, displacement, factor-of-safety.
- **Modal** — first N natural frequencies and mode shapes (almost free
  on top of linear static).
- **Bonded contact in assemblies** — multi-body studies, parts tied at
  touching faces. No friction yet.
- **Compute targets:** local subprocess (OSS, gmsh+ccx on PATH) and
  cloud worker (hosted, same `.fem` job spec). Queue mirrors the
  STEP-tessellation pattern.
- **Renderer:** stress-colored mesh with displacement-scale slider;
  mode-shape playback for modal results.
- **LLM tool:** single `fem_run({ source_file, materials, fixtures,
  loads, studies, mesh_size })` returning max stress, max displacement,
  FoS, modal frequencies, and a result-file ID. Doc page at
  `backend/internal/llm/docs/fem.md` per the consolidated tool pattern.

### Dependencies

Sits after Phase 3 (viewport face selection). Realistic boundary
conditions need stable face references on a B-rep — only `.feature`
files have those — and the BC-picking UX needs viewport face-clicking.
A `.jscad` fallback (faces by normal/region) is possible later, not v1.

### Phase ordering inside FEM

- **F1.** Linear static + modal + bonded contact, local + cloud
  workers, single LLM tool.
- **F2.** Frictionless contact, multi-step loading, anisotropic materials.
- **F3.** Thermal + thermal-mechanical (likely add Elmer alongside CalculiX).
- **F4.** Frictional contact, plasticity / hyperelastic, dynamic
  implicit/explicit. Multi-quarter; only with demand.

### Non-goals

- CFD — different solver, different culture; far future under a
  separate flow-simulation file kind.
- In-browser solver. MFEM-WASM is interesting, but real solves take
  seconds-to-minutes; server roundtrip is not the bottleneck. The
  `.fem` spec is solver-agnostic so a WASM backend can drop in later
  without data-model changes.
- Topology optimization — adjacent but separate workflow.

---

## Mechanical advanced capabilities (Tier 1)

A grouped cluster of mechanical-CAD-grade features that ship after the
parametric foundation + Phase 2/3 are in. Each follows the FEM pattern
— minimal v1, doc page in `backend/internal/llm/docs/`, single LLM
tool, OSS test scenario — at tighter scope.

Order is dictated by dependencies:

```
materials database  ──► parallel, anytime
3D mates (Tier 0)   ──► after Phase 3; unblocks motion + tolerance + FEM contact
tolerance stack-up  ──► after mates
CAM toolpaths       ──► after Phase 2; can parallel mates
topology optim.     ──► after FEM (FEM in a loop)
```

### Materials database

Cross-cutting: FEM (mech + thermal), tolerance (thermal expansion),
drawings (material callouts), Library Parts (default material), and
the architecture project type (building materials) all need a single
source of truth.

- **File kind:** `.material` files inside Library projects, same
  visibility / verified-publisher pattern as `.part`.
- **Properties (v1):** E, ν, ρ, α, yield, ultimate, k, cₚ. Optional:
  S-N curves, stress-strain curves.
- **Seed dataset:** ~500 common engineering materials (steels,
  aluminums, titaniums, copper, plastics, woods, plus building
  materials: concrete, brick, timber, glass, insulation) shipped as
  `kerf-system/materials` with the verified-publisher badge.
- **API:** `kerf.materials.find({...})` returns a reference consumable
  by FEM, Part defaults, tolerance studies, architecture walls/slabs.
- **Phasing:** Mat1 (`.material` kind + seed + FEM consumes). Mat2
  (Parts get default-material field; BOM gains material column). Mat3
  (distributor stock grades).

### 3D assembly mates (Tier 0)

The single biggest unblock — required for motion sim, FEM contact,
tolerance stack-up.

- **Mate types (v1):** coincident, concentric, parallel,
  perpendicular, distance, angle, tangent — between faces, edges,
  vertices, axes.
- **Solver:** investigate planegcs's 3D mode first; fallback is
  **SolveSpace's solver** (GPL3, subprocess only) — most
  production-grade open option.
- **Storage:** new `mates: [...]` array on `.assembly` files; refs use
  Component-relative face IDs.
- **LLM tool:** `add_mate({ type, refs[], value? })`.
- **Phasing:** M1 (basic mates + headless solver). M2 (drag-to-solve +
  conflict highlighting). M3 (motion-study mode: parameterize a mate,
  sweep, animate).
- **Dependencies:** Phase 3 face selection.

### Tolerance stack-up

The analysis layer on top of GD&T frames (already shipped on drawings).

- **Inputs:** two faces (from-face → to-face); the dimension graph
  walks the assembly via mates to find the chain.
- **Methods (v1):** worst-case (sum) and RSS (root-sum-square).
- **Phasing:** T1 (1D worst-case + RSS, min/max distance report). T2
  (Monte-Carlo for non-Gaussian distributions). T3 (3D tolerance
  allocation).
- **LLM tool:** `tolerance_stack({ from_face, to_face, method })`.
- **Dependencies:** 3D mates.

### CAM toolpath generation

Closes the design-to-manufacture loop — next "real engineering output"
pillar after FEM.

- **Library:** **OpenCAMlib** (LGPL 2.1) — used by FreeCAD Path; mature.
  Subprocess on backend; consider WASM in-browser later (~5 MB gz).
- **Operations (v1):** face mill, contour, pocket, drill, profile.
  2.5D only.
- **Output:** G-code with selectable post-processor (LinuxCNC, GRBL,
  Mach3, Fanuc). Toolpath polylines render in the 3D viewport.
- **File kind:** `.cam` — JSON job spec referencing a `.feature`
  source; operation stack same shape as FEM's load-case stack.
- **LLM tool:** `cam_run({ source_file, operations[], post_processor })`.
- **Phasing:** CAM1 (2.5D ops + viewport preview + G-code). CAM2 (3D
  parallel + waterline). CAM3 (lathe + 5-axis). CAM4 (cycle-time +
  collision via CAMotics).
- **Dependencies:** Phase 2 `.feature`.

### Topology optimization

"Make this bracket 30% lighter." Killer chat-driven demo once FEM is in.

- **Solver:** **CalculiX SIMP** (built into newer CalculiX) is the v1
  pick — same binary already invoked for FEM. Alternative: **ToOptix**
  (GPL3) for level-set methods.
- **Output:** density field on the mesh → marching-cubes to a new
  mesh. Feature-tree reconstruction is hard; punt to a manual remodel.
- **File kind:** `.topo` — references a `.feature`, defines design
  space + fixed regions; load cases reuse FEM's `fixtures` / `loads`
  vocabulary; adds volume-fraction target.
- **LLM tool:** `topo_run({...})` → optimized mesh + summary metrics.
- **Phasing:** O1 (CalculiX SIMP wrapper + density viz). O2 (mesh
  export). O3 (multi-load-case + manufacturing constraints, e.g.
  3D-print overhang).
- **Dependencies:** FEM landed.

---

## Multi-domain support: project types

A `project_type` enum on the project row is the natural seam for taking
Kerf beyond mechanical CAD into adjacent domains. The chat/files/revisions
plumbing stays shared; the **type gates** which renderer loads, which LLM
tools are exposed, and which file extensions are valid in that project.

### Initial types

| Type | Modeling kernels | Native file kinds | LLM tool surface | Renderer |
|---|---|---|---|---|
| **mechanical** *(today's default)* | JSCAD + (Phase 2) OCCT + (post-P3) CalculiX | `jscad`, `sketch`, `assembly`, `drawing`, `step`, `feature`, `fem` | feature/sketch/assembly/drawing/fem tools | Three.js 3D + 2D drawing canvas |
| **electronics** | [tscircuit](https://tscircuit.com) (TSX → Circuit JSON) | `circuit.tsx`, `circuit.json`, `netlist` | place-component, connect, set-outline, run-DRC, compile | tscircuit schematic + PCB + 3D-board viewers |
| **architecture** | text-DSL → IFC (IfcOpenShell, LGPL) | `bim`, `ifc`, `drawing`, `sketch`, `material` | wall/slab/opening/space/level ops, IFC compile, BOQ | 2D floor-plan + 3D building view (web-ifc + Three.js) |

Each type ships a sub-package under `src/projectTypes/<name>/` that contributes:
- A renderer component
- A file-tree create menu
- A toolset of LLM tools (registered at boot)
- A set of valid file kinds (validated by handlers)

The LLM system prompt has a per-type addendum so the model knows what tools
it has and the conventions for that domain.

### Migration path
- Add `project_type text not null` to `projects`. Backfill all existing rows to `mechanical` in the same migration; afterwards the column has no default — every new project must declare its type.
- "Create project" requires picking a type up front (no implicit fallback). The picker is the first step of project creation, before naming.
- Workshop is **multi-type from day one**: a single shared gallery surface, with `type` as a filter chip and a per-type result thumbnail (3D render for mechanical, board preview for electronics, floor plan for architecture). Forking preserves the source project's type. Search index, like/fork counts, and insert-from-workshop dialogs all gain a `type` filter and respect type compatibility (e.g., you can only insert an electronics workshop project as a part inside a mechanical project — see cross-domain link below).

### What this is NOT
- It is **not** a way to magically import KiCad or Revit files (those are
  separate import projects under each type).
- It is **not** a runtime-pluggable extension system. Types are built into
  the binary; adding a new one is a code contribution, not a plugin.

---

## Electronics: tscircuit integration (planned)

The first non-mechanical type. Picked because tscircuit's "TSX components
→ Circuit JSON" model maps almost 1:1 onto how Kerf already drives
`.jscad`: the LLM edits a text file, a worker compiles it to a viewable
artifact, file revisions give us undo. Same chat-loop, same diff
semantics, same revisions panel.

### Stack

- **`@tscircuit/core`** — TSX → Circuit JSON compiler.
- **`@tscircuit/pcb-viewer`** + **`@tscircuit/schematic-viewer`** — in-browser 2D renders.
- **`@tscircuit/3d-viewer`** — assembled-board GLTF (board + component bodies).
- **Circuit JSON** — durable intermediate, stored alongside the TSX so
  views can render without re-bundling user code on every load.

### File kinds (electronics project)

```
.circuit.tsx   tscircuit source                 (LLM edits this; the chat-loop target)
.circuit.json  compiled Circuit JSON            (server-rendered cache, derived)
.netlist       SPICE netlist for simulation     (later phase)
.symbol        custom symbol/footprint          (later phase)
```

The TSX is the source of truth; the JSON is a derived artifact, but it
*is* persisted (and revisioned alongside the source) so we can render
schematic / PCB / 3D without running an in-browser bundler on read.

### LLM tool surface (electronics-only registry)

- `place_component({ type, value, refdes?, at? })`
- `connect({ from: "R1.pin1", to: "C1.pin2" })`
- `set_board_outline({ shape: "rect" | "custom", w?, h?, sketch_file? })` — accepts a `.sketch` reference for irregular outlines
- `run_drc()` → list of design-rule violations
- `compile()` → re-derive `.circuit.json` + 3D GLTF + outline SVG

### Renderer (Editor route, dispatched on `project_type`)

- Tabbed schematic / PCB / 3D-board surfaces, replacing the JSCAD viewport.
- Chat panel, file tree, revisions panel, assembly insert dialog — all
  kernel-agnostic and reused unchanged.

---

## Architecture: IFC + text-DSL (planned)

The architectural project type, and the path to "Revit-level over
time" done right for the LLM era. Revit's moat is the BIM data model,
not the UI; **IFC** (Industry Foundation Classes) is the open
equivalent the entire AEC industry has settled on. We use IFC as the
canonical data model and ship a higher-level text-DSL on top — the
LLM edits DSL, a compiler emits IFC, the renderer reads IFC.

### Stack

- **Canonical model: IFC 4.x** (ISO 16739). STEP-based, text-encodable,
  spec public. We implement a subset; same trajectory Revit followed
  for two decades.
- **Library: IfcOpenShell** (LGPL 2.1) — mature C++/Python reader /
  writer / query engine. Subprocess on backend; LGPL is dynamic-link
  clean even bundled. Same license posture as gmsh / ccx.
- **Browser viewer: web-ifc** (Apache 2.0) + **IFC.js / @thatopen** —
  WASM IFC parser + Three.js viewer. MIT/Apache; embeddable.
- **Bonsai (formerly BlenderBIM)** — reference open implementation
  of an IFC-native authoring tool. Studied; not a runtime dependency.

### Source of truth: text-DSL → IFC

The user-facing file is a declarative DSL — readable, diffable,
LLM-tractable. The compiler maps DSL constructs to IFC entities and
persists both. Same pattern as JSCAD → mesh and tscircuit → Circuit
JSON: text source, derived artifact, both revisioned.

DSL example (illustrative; final surface TBD during A1 spike):

```
building "house" {
  site { lat: -33.918, lon: 18.423, orientation: 270deg }

  level "ground" elevation: 0 {
    wall w1 from (0,0)  to (10,0) height: 3.0 thickness: 0.2 type: "brick"
    wall w2 from (10,0) to (10,8) height: 3.0 thickness: 0.2 type: "brick"
    wall w3 from (10,8) to (0,8)  height: 3.0 thickness: 0.2 type: "brick"
    wall w4 from (0,8)  to (0,0)  height: 3.0 thickness: 0.2 type: "brick"

    slab    floor bounds: [w1, w2, w3, w4] thickness: 0.15 type: "concrete"
    space   "living-room" bounds: [w1, w2, w3, w4]

    door    in: w1 at: 2.0 width: 0.9 height: 2.1
    window  in: w2 at: 4.0 width: 1.2 height: 1.5 sill: 0.9
  }

  level "first" elevation: 3.0 { ... }

  roof gable pitch: 30deg eaves: 0.6 covers: ["ground", "first"]
}
```

### File kinds (architecture project)

```
.bim       text-DSL source        (LLM edits this; chat-loop target)
.ifc       compiled IFC bytes     (derived, persisted, revisioned,
                                   exportable to Revit / ArchiCAD)
.drawing   architectural drawings (floor plans, sections, elevations —
                                   reuses existing drawing infra)
.sketch    irregular outlines     (site plans, complex space boundaries —
                                   reuses existing sketcher)
.material  building materials     (shared with mechanical materials database)
```

### Renderer

- **Floor-plan 2D** — top-down clean line drawing per level. Section
  cuts. Annotation. Reuses the existing `.drawing` infra.
- **3D building view** — Three.js + web-ifc/IFC.js. Walk-through
  camera controls. Layer toggles per level / per discipline
  (architecture / structure / MEP).
- **Section views** — vertical or horizontal cut planes with hatched
  cut surfaces.

### LLM tool surface (architecture-only registry)

- `add_wall({ from, to, height, thickness, type })`
- `add_slab({ bounds, thickness, type })`
- `add_opening({ in: wall_id, kind: "door"|"window", at, width, height, sill? })`
- `add_space({ name, bounds })`
- `add_level({ name, elevation })`
- `set_site({ lat, lon, orientation })`
- `compile_ifc()` — re-derive `.ifc` from `.bim`
- `quantity_takeoff()` — BOQ (areas, volumes, material counts)
- `export_ifc()` — IFC file ready for Revit / ArchiCAD round-trip

The model can also `edit_file` the `.bim` text directly; recompile is
automatic on save (same pattern as JSCAD).

### Phasing

- **A1.** "House primitives" minimum: project_type=architecture,
  `.bim` DSL parser, IfcOpenShell-backed compiler, basic entities
  (wall, slab, opening, space, level, site), 2D floor-plan render,
  3D viewer via web-ifc.
- **A2.** Doors/windows as parametric openings with hardware
  (hinges/handles); furniture catalog from Library; section views
  in drawings.
- **A3.** Roofs (gable, hip, flat), staircases, railings.
- **A4.** Multi-building site plans; terrain integration; topo from
  GeoJSON.
- **A5.** MEP runs — basic ductwork, plumbing, electrical conduits +
  fixtures (lights, outlets, panels) via IFC4 MEP entities.
- **A6.** Quantity takeoff (BOQ) — areas per material / per space,
  cost rollup; CSV export.
- **A7.** IFC import — round-trip Revit / ArchiCAD models into the
  kerf model.
- **A8.** Rebar / structural reinforcement (IFC structural domain).
- **A9.** Clash detection between disciplines (architecture vs MEP
  vs structural). Punt to standalone tooling at first; integrate later.

### Cross-domain links

- **`materials` Library** is shared between mechanical and architecture
  — same `.material` kind, same verified publishers, same database.
  An aluminum casting alloy and structural concrete coexist.
- **`drawings`** are kernel-agnostic; floor plans and architectural
  sections reuse the dimension / annotation / sheet infrastructure
  already shipped for mechanical.
- **`sketch`** outlines drive irregular spaces and site boundaries.

### Non-goals (architecture)

- **Full Revit parity v1.** Implementing the IFC subset that covers
  80% of real architectural design takes years; that's exactly what
  Autodesk + ArchiCAD have done. We ship a useful slice early and
  expand iteratively.
- **CFD / HVAC simulation.** Different solver, different culture; far
  future.
- **Structural FEA.** The mechanical FEM stack will not directly
  apply — buildings need beam / shell / plate elements, not solid
  mech. Possibly later via Code_Aster or a building-FEA-specific path.
- **Real-time collaborative editing.** Same posture as the rest of
  the product; deferred indefinitely.
- **Cost estimation beyond quantity takeoff.** Costing is a regional
  / contractor / supplier problem; we expose quantities and let users
  bring their own pricing.

---

## Cross-domain link: PCB-as-part in a mechanical assembly

The single feature that justifies one Kerf binary over two sibling
tools: a mechanical project can reference a PCB from an electronics
project as a positioned part, so the enclosure designer is always
working against the live board outline and the assembled component
heights.

### Data-model extension (assembly Component rows)

Today a Component points at a file inside the same project. We extend
the source descriptor to allow other projects:

```
component {
  id, parent_assembly_id, transform (mat4),
  source: {
    kind: "file"             // existing — same-project file reference
        | "external_project" // new — cross-project artifact reference
    project_id?    // for external_project
    file_id?
    revision_id?   // null = "track latest"; set = pinned to that revision
    artifact:      // which facet of the source we're consuming
      "board_3d"          // assembled board GLTF
      | "board_outline_2d"  // board edge as a sketch profile
      | "model_3d"          // (future) any 3D model exposed by the source project
  }
}
```

Two artifacts a mechanical project can consume from an electronics one:

1. **`board_3d`** — assembled-board GLTF. Inserts as a regular Component:
   gets transforms, clearance checks, collision against enclosure walls.
2. **`board_outline_2d`** — board edge polyline as a sketch profile.
   Useful for designing an enclosure cutout, screw-pattern, or
   mounting-plate footprint from the same source-of-truth.

### Build pipeline (server-side, on electronics-project save)

- TSX → Circuit JSON → cached as a `.circuit.json` revision.
- Circuit JSON → GLTF (headless `@tscircuit/3d-viewer`) → cached as a
  derived artifact keyed by the electronics revision ID.
- Circuit JSON → board outline SVG/Geom2 → cached the same way.

Derived artifacts live in a `derived_artifacts` table (or as a
soft-deleted file kind in the electronics project — TBD) keyed by
`(source_revision_id, artifact_kind)`. They're regenerated lazily on
first request and cached forever; they get garbage-collected when the
source revision is purged.

### Reference resolution (mechanical render path)

- **Pinned** (`revision_id` set): fetch the cached artifact for that
  exact revision. Stable; assembly never changes unless the user
  re-pins.
- **Tracking** (`revision_id` null): fetch the artifact for the
  source's HEAD revision. The Component is flagged "out of date" in
  the assembly tree when the source advances; user can re-accept (which
  pins to the new HEAD) or pin back to a known revision.

### UX

- **Insert-part dialog** gains a "From another project" tab next to the
  existing "From this project" / "From workshop" tabs. Picker chooses
  source project → file → artifact, plus a transform.
- **Workshop insert** also surfaces electronics projects when the
  current edit context is a mechanical assembly, filtered to projects
  that publish a `board_3d` or `board_outline_2d` artifact.
- Referenced PCBs render with a subtle visual treatment (green tint /
  boundary box) so they're distinguishable from in-project geometry.
  Clicking opens the source electronics project in a new tab.

### Phasing

1. **e1.** `project_type` column + UI route dispatch + create-project picker. No electronics editor yet — just the seam, with workshop type-filter wired up so the substrate is in place.
2. **e2.** Electronics project type with tscircuit editor, schematic/PCB viewers, basic LLM tools. No cross-linking. Workshop accepts electronics projects.
3. **e3.** Server-side Circuit JSON + 3D + outline derivation pipeline (cached, revision-keyed).
4. **e4.** Cross-project Component references (electronics → mechanical) with pinned and tracking modes. Insert dialog "From another project" tab.
5. **e5.** Bidirectional hint: mechanical-defined enclosure interior shape feeds back as a board-outline constraint in the source electronics project.

### Non-goals (this phase)
- KiCad/Eagle direct import (separate import-tooling phase; Circuit JSON converters exist upstream).
- Real circuit simulation in the LLM loop (SPICE-via-WASM is a follow-up phase).
- Layout autorouting beyond tscircuit's defaults — punt upstream.

---

## Library / Workshop split

Today `/api/workshop/parts` does double duty — it's both a Workshop sub-tab
("browse public parts") and the only way users discover other people's parts.
That conflates two distinct purposes:

- **Workshop** is project showcase. *"Look what people built, fork it,
  learn from it."* Social, inspirational. Forks an entire project as a new
  starting point.
- **Library** is parts catalog. *"I need an M3 screw / 555 timer /
  NEMA17 stepper to drop into my current assembly right now."* Functional.
  Picked into existing work via a popup, never forked as a project.

### Plan

1. **`/library` top-level route** — parts-focused UI: search, category
   filter, verified-publisher badge, click → details panel with photos
   and distributors. Reuses the existing `/workshop/parts` SQL.
2. **`LibraryPicker` modal** — same data, used by AssemblyEditor's
   *Add component*. Replaces today's project-local dropdown. Searches
   the global Library plus the current project's parts side-by-side.
   Later wired into CircuitEditor's `cad_component` resolution and any
   "place part" tooling in drawings.
3. **Backend: `/api/library/parts`** as the canonical endpoint,
   `/api/workshop/parts` kept as a deprecated alias for one release.
4. **Curation via existing `is_verified_publisher`** — no new tables.
   First-party stock parts (M3×10 screws, etc.) live as a real
   `kerf-system` account's project files; verified-publisher rows
   float to the top of the Library. Same edit/publish flow as any user.
5. **Sharing model mirrors Workshop** — per-Part `visibility='public'`
   field gates inclusion (already present), parent project must not be
   `private` (already enforced). Adding a *Publish to Library* affordance
   on `LibraryEditor` mirrors `PublishButton`'s UX (slug, description,
   thumbnail).

Workshop stays focused on project listings. Library becomes the
discovery surface for individual parts.

---

## BOM rework

`/projects/:id/bom` today is a standalone read-only route divorced from
the model. The intended UX is the opposite:

- **Inline panel inside AssemblyEditor** — collapsible region under the
  component tree, so the BOM updates as you edit and you see the part
  count next to the 3D view.
- **Editing affordances** — quantity overrides (override a rolled-up
  count without restructuring the assembly), non-stocked flags, per-row
  notes. Persisted on the Assembly file, not in a separate table.
- **Distributor data UX** — surface MOQ, lead time, and alternates
  inline. Manual *Refresh prices* button (Library Phase 2 will make this
  automatic).
- The current `/bom` route can stick around as a printable / exportable
  view backed by the same endpoint.

---

## Electronics objects/features fix

CircuitEditor today is a tabbed full-bleed editor (Source / Schematic /
PCB / 3D) — but the editor's left-bottom panel still shows the JSCAD
`ObjectsPanel`, which has nothing to do with circuits. The 3D tab
synthesizes box approximations on the fly from the compiled CircuitJSON.
That's the wrong abstraction.

- **Circuit-specific panel** — replace `ObjectsPanel` for `kind='circuit'`
  files with a Components/Nets list parsed from the compiled CircuitJSON
  (refdes, value, footprint). Updates as the source compiles.
- **Resolve `cad_component` via Library** — when a circuit references
  `cad_component={fileId}`, the 3D tab pulls the actual Library Part's
  geometry instead of rendering a box. Closes the loop with the
  Library-picker work above.
- **Bidirectional link** — picking a part in the Components list
  highlights it on the schematic + PCB + 3D simultaneously
  (cross-view selection sync, mirroring how the mechanical
  ObjectsPanel ↔ Renderer already work).

---

## Phase 4: Rhino-tier surfacing

Industrial-design-level workflows. Multi-quarter project, only if there's
demand for it:
- Sweep1 / Sweep2, network surfaces, blend surfaces, match surfaces.
- Surface continuity analysis (G0/G1/G2/G3).
- Optional SubD modeling via [OpenSubdiv](https://graphics.pixar.com/opensubdiv/).

---

## Performance roadmap (formerly PERFORMANCE.md)

### Phase 1: frontend perf fundamentals — ✅ shipped
- JSCAD eval moved to a Web Worker
- Lazy topology (compute only when measure/drawing tools subscribe)
- File-size-scaled re-eval throttle (250 ms → 3 s for huge files)
- IndexedDB mesh cache keyed by content hash
- Vite manualChunks bundle split (1.6 MB main → 520 KB / 156 KB gzipped)

### Phase 2: reliable STEP uploads — ✅ shipped
- Chunked / resumable upload protocol with SHA-256 integrity
- Polling progress endpoint
- 5 MB chunks, 200 MB cap (configurable)
- Janitor sweeps stale sessions hourly

### Phase 3: server-side STEP pre-tessellation — 📋 next
Once Phase 2 stabilizes, browser STEP parsing is the next pain. Three
options to evaluate:

- **A. wazero + occt-import-js WASM** — pure-Go runtime, single binary still ships. Glue is fiddly.
- **B. Node sidecar** — zero new code (Node already runs occt-import-js). Adds Node to the deploy.
- **C. CGO bindings to OpenCASCADE** — fastest, heaviest build chain.

Lean toward A; fall back to B if WASM glue gets thorny.

After upload finalize: insert a `step_tessellation_jobs` row, background
worker runs OCCT, produces `.glb`, frontend prefers the glb to re-parsing the
STEP.

### Phase 4: revision DB efficiency — 📋 next
- Diff-based revisions (Myers diff): base every N rows + diffs in between.
- Compress `content` column (gzip in app, `bytea` on disk).
- Combined: ~50× shrink for typical edit patterns.

---

## Cloud (hosted-tier) roadmap

The cloud tier is proprietary (see [cloud/LICENSE](./cloud/LICENSE)). The
public-facing OSS doesn't depend on any of it; everything below `cloud/` is
add-on functionality for the hosted service.

| Capability | Status |
|---|---|
| Paystack billing (USD-priced, ZAR-settled) | ✅ shipped |
| Workshop (free CAD-design sharing gallery) | ✅ shipped |
| Project 3D thumbnails (client-side render-on-save) | ✅ shipped |
| Git (commits + branches + merge + GitHub sync) | ✅ shipped |
| Multi-lane git graph | ✅ shipped |
| Stateless object-storage git backend | 🚧 in flight |
| Email notifications (account, billing) | 🔮 planned |
| Multi-user real-time editing | 🔮 deferred indefinitely |

---

## Documentation roadmap

- **README.md** — front door, quickstart, build, links. *Improving.*
- **ROADMAP.md** — this document.
- **CONTRACT.md** — API + data model spec. Reference for agents and contributors.
- **`docs/`** — extended guides (planned). Sketching, assemblies, drawings,
  cloud, contributing, architecture deep-dive.
- **Landing page** (`src/routes/Landing.jsx`) — *being revamped.*
- **`backend/README.md`** — backend-specific dev guide.
- **`cloud/README.md`** — cloud-tier build/deploy.

---

## How to contribute

- **OSS contributions** are welcome under the MIT license. Pick anything
  marked 📋 or 🔮 in the table above.
- **Cloud contributions** require a separate license agreement; reach out
  before opening PRs against `cloud/` paths.
- **Bug reports**: GitHub Issues.
- **Architecture discussions**: GitHub Discussions when we open one.

The code structure mirrors this roadmap: `backend/internal/` is OSS Go,
`backend/cloud/` is cloud Go (build-tagged), `src/` is OSS frontend,
`src/cloud/` is cloud frontend. New features land in the right tree based on
their license.
