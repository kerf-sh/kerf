# What's New

Recent features shipped to Kerf. See [ROADMAP.md](https://github.com/kerf-sh/kerf/blob/main/ROADMAP.md) for the full list and status of every item.

## Sprint — 18 May 2026 — git-as-project / CLI / PLC-LD / firmware / joints / imports / BIM / SubD / civil / marine / render / clash / nesting

A large feature sweep landed across every major discipline. All items below are shipped and integrated on main.

### Every project is a real git repo

Every Kerf project is now a cloneable git repository. Large files are
auto-handled (stored as pointer objects in object storage). Forking a project
is near-free — shared immutable blobs mean you pay only for diverged content.
Both **GitHub and GitLab** mirror connections are supported. The CLI exposes
the full sync surface:

- `kerf sync` — two-way folder sync between a project and a local directory
- `kerf export` — snapshot export to a local folder
- `kerf import` — import a local folder into a new or existing project
- `kerf hydrate` — resolve large-file pointers and download binary assets

### One client: `pip install kerf`

The single install path for end users is now **PyPI**. There is no Homebrew
formula.

```sh
pip install kerf          # cloud-default client + CLI
pip install 'kerf[server]'   # full self-host: bring-your-own Postgres + kerf serve
```

`pip install 'kerf[server]'` followed by `kerf serve` brings up the full
server stack. Requires Postgres. See [local-install.md](./local-install.md).

### PLC: IEC 61131-3 Ladder Diagram editor

A visual Ladder Diagram editor is now available alongside the existing
Structured Text (ST) editor. Both conform to IEC 61131-3. Switch between LD
and ST within the same `.plc` file.

### Embedded / firmware: Arduino + PlatformIO

New embedded/firmware workflow:

- Arduino `.ino`/`.uno` file kinds are first-class project files.
- C/C++ embedded source supported.
- PlatformIO-style build and flash toolchain for common MCU targets.

### Full mechanical joint system

Assemblies now carry a complete mechanical joint type set: **rigid, revolute,
slider, cam, gear, and pin-slot** joints. Pair this with the FEM nonlinear
plasticity solver (also landed) for structural simulation that follows
material failure past the elastic limit.

### Import breadth

New importers and export targets:

- **DXF/DWG** — round-trip for 2D drafting interchange.
- **ECAD formats** — Eagle, Allegro, PADS, and gEDA schematics/layouts import
  into the Kerf electronics workspace.
- **Fab outputs** — Gerber, Excellon, Pick & Place, IPC-2581, and ODB++ bundle
  export all wired up.

### BIM: parametric families + extended building elements

BIM authoring expanded significantly:

- **Parametric family authoring** — author your own `.family.json` components
  with type/instance parameters, formulas, and scheduling metadata.
- **Parametric family library** — a built-in catalog of door, window, slab,
  beam, and column families.
- **Extended building elements** — walls, doors, windows, slabs, stairs, and
  ramps are all now parametric and hosting-aware.
- **Structural grid and framing** — column/beam grids with structural member
  profiles.
- **Site toposolids** — terrain surface from survey points with earthwork
  volumes.
- **Material catalogue** — BIM-grade material library with render appearance
  and schedule properties.

### SubD authoring with creases

Catmull-Clark subdivision surface authoring is now available, including
**crease** support for sharp edges on organic forms. Pair with the existing
quad-remesh and mesh-repair tools.

### Civil: geospatial CRS + TIN terrain

Civil engineering workflow additions:

- Geospatial coordinate-reference-system (CRS) support — attach a project to
  a real-world datum (WGS-84, local UTMs).
- TIN terrain surfaces from point-cloud / survey data.

### Marine: NURBS hull-fairing

Marine hull design: NURBS hull-fairing workflow for smooth developable
surfaces, targeting naval architecture and small-craft design.

### Photoreal render path

The Cycles-based render path is now end-to-end:

- **Scene translator** — maps Kerf PBR materials to the render shader graph.
- **Render worker** — headless worker queues, executes, and caches renders by
  scene hash.
- **Hero render panel** — resolution presets (1 K / 2 K / 4 K), sample count,
  HDR environment selection, start / cancel / download.
- **GPU pricing meter** — cloud installs meter GPU-seconds in the `kerf_paid`
  bucket at cost + markup.
- **In-browser fallback** — `three-gpu-pathtracer` progressive path tracer for
  offline and self-hosted use.

### Cross-discipline clash detection

Clash detection across multiple disciplines (mechanical + electrical +
structural + BIM) in a single federated model view. Select clash pairs,
inspect clearances, and export a clash report.

### Nesting / cut-optimisation + layout view

2D sheet-metal nesting and cut-optimisation for flat parts: places contours on
a stock sheet with configurable kerf and spacing, reports material utilisation,
and exports the layout as DXF.

### Education / maker on-ramp

Guided on-ramp projects for education and maker use: simplified UI mode,
pre-built example projects, and a streamlined first-run experience.

### Large-assembly LOD

Level-of-detail (LOD) management for large assemblies: automatically swap
in simplified meshes beyond a configurable part count or bounding-box threshold,
keeping frame rates interactive on assemblies with thousands of components.

### Broadened text/code file editing

The chat and file editors now support a wider set of text and code file kinds
(Markdown, plain text, CSV, JSON, YAML, XML, Python, and others) directly
within a project, without leaving the Kerf workspace.

### App version in Settings

The **Settings** panel now shows the running server version and build commit,
making it easy to confirm which release is deployed.

---

## Sprint — 17 May 2026 (later) — compare hub matrices, scroll-to-top, CFD foundation, FEM ref-values

What's new this sprint: the [Compare hub](/compare) now shows per-category
feature matrices for Mechanical, Electronic, BIM, Jewelry & NURBS, and DCC,
with **14 head-to-head comparison pages** wired (Altium, Autocad, Blender,
Civil3d, Freecad, Fusion, Inventor, KiCad, MatrixGold, Max3ds, Onshape,
Revit, Rhino, Solidworks). The Roadmap link now sits in the public topbar
alongside Docs and Compare; scrolling to the top on every route change
means no more landing mid-page on `/compare`. The Render pipeline's
backend Blender Cycles + browser `three-gpu-pathtracer` architecture is
now formally scoped in `tasks.md` as **T-106a..f** (scene translator,
Cycles worker, hero-render UX, GPU-seconds → `kerf_paid` pricing meter,
self-host docker, in-browser fallback). A **CFD foundation** landed —
`kerf_fem.cfd_potential` (potential flow, `Cp(θ) = 1 − 4 sin²θ` analytic
oracle) + `kerf_fem.cfd_navier_stokes` (lid-driven cavity, Ghia Re=100
reference), 61 hermetic CFD tests in `test_cfd.py`, **2-D laminar
scope** — and a **FEM reference-value suite** with citable Roark /
Blevins / Incropera oracles (`pressure_load.py` + 43-test
`test_fem_refvalues.py`, 42 green, one ASTM E1049 rainflow test skipped
with the real bug flagged). A defensive `body { max-width: 100vw }` +
`overflow-x: clip` CSS guard kills the site-wide h-scroll quirk in
Safari/WebKit. **24 134 tests green** across the full repo
(via `pytest --collect-only`).

## Sprint — 17 May 2026 — geometry kernel keystone + history DAG + boot loader + docs viewer + comparison expansion

Five user-facing wins landed together:

- **B-rep topology keystone + tolerant pure-Python solid booleans** — the
  pure-Python geometry kernel now emits topologically validated solids
  end-to-end; cut / fuse / common run without OCCT and return watertight
  2-manifold bodies. Detail in the kernel section below.
- **Parametric history DAG with persistent face / edge naming** — edit an
  upstream parameter and a downstream fillet still targets the
  *semantically same* edge, not a different one (`feature_id::role::
  fingerprint` three-part selectors).
- **Pre-React boot loader** — Kerf-branded SVG triangles loader paints
  immediately in `index.html`, then transitions cleanly into the first
  React route. No more blank screen on first load.
- **Docs viewer redesign** — grouped sidebar (domains + workflows + cloud
  + reference + develop), breadcrumbs, TOC, audit-filter; manifest
  generation now emits the grouped taxonomy automatically.
- **Comparison pages expanded** — Altium, MatrixGold, Blender, Onshape
  are new; FreeCAD, KiCad, Rhino, Revit, Fusion pages were deepened.
  Nine head-to-head comparison pages now live under `/compare/`.
- **Renderer hero / PBR upgrade** — 2048×2048 4× supersample,
  ACES tonemap, PMREM-pre-filtered RoomEnvironment HDRI, and bloom — one
  production-grade lighting path shared by Workshop covers, share-cards,
  and the primary 3D viewport.
- **Frontend touch + responsive polish** — Renderer + Gumball touch
  gestures, Editor responsive layout, top-bar overflow, Docs mobile
  drawer.

## Sprint — mid-May 2026 — geometry kernel step-change

The pure-Python geometry kernel went from "approximate circles, broken or
delegated booleans, no parametric history" to a real math-depth moat: every
analytic builder now emits a topologically validated solid; cut / fuse /
common booleans run in pure Python with a tolerance-aware shell sewer and
return a watertight 2-manifold body; edges fillet with verified G1/G2
continuity and chamfer with constant / asymmetric / variable widths; surface,
curve, and loop offsets land with exact-distance oracles; the closest-point
primitive everything else builds on is in place; surface–surface intersection
is hardened (with a long-standing rational-weight bug fixed); and the kernel
now carries an in-process parametric **history DAG** with persistent face /
edge naming — so editing an upstream parameter regenerates the downstream
fillet against the *semantically same* edge, not a different one. **620
hermetic analytic-oracle-asserted kernel tests are green; the full repository
collects 23 902 tests, ship-gate clean.** Detail and the next P2 (pure-Python
STEP/IGES + SubD↔NURBS + mesh→NURBS autosurface + 2D region boolean) step
live in
[`docs/plans/geometry-kernel-roadmap.md`](./plans/geometry-kernel-roadmap.md).

## Sprint — May 2026

### Plugin architecture + monorepo

The backend has been split into a `packages/kerf-*/` plugin monorepo. Nineteen
independent packages discovered via Python entry points (`kerf.plugins` group),
each advertising a `provides=[...]` capability list at boot. The previous
`backend/` and `pyworker/` trees are retired; install personas
(`api-only` / `mech` / `electronics` / `bim` / `full` / `compute-only`) pull the
relevant subset. Runtime capability tags are inspectable at
`GET /health/capabilities`. See [architecture.md](./architecture.md) and
[capabilities.md](./capabilities.md).

### kerf-sdk (Python SDK)

New `kerf-sdk` package on PyPI (`pip install kerf-sdk`). A thin Python client
for the `/v1/rpc` endpoint — drives the same tool surface the chat LLM uses,
from your own machine. Authenticates with an API token (`KERF_API_TOKEN`).
Replaces the previously-rejected TS Web Worker scripting plan.

### kerf-server CLI

Single CLI entry-point: `kerf-server [--config ...] [--migrate]`. Drops in for
`uvicorn backend.main:app`. Provided by `kerf-core`.

### Cloud retired into plugins + root LICENSE-CLOUD

The legacy `cloud/` and `backend/cloud/` trees collapsed into two proprietary
plugin packages: `packages/kerf-billing/` and `packages/kerf-cloud/`.
`LICENSE-CLOUD` sits at the repo root. Operator docs moved to
[cloud-operator.md](./cloud-operator.md).

### FEM polish

Deformed-mesh overlay in the viewport, SLEPc + CalculiX modal analysis,
multi-material BCs. `kerf-fem` now advertises `fem.linear-static`,
`fem.modal`, and `fem.thermal` whenever the relevant solver is available.

### CAM polish

Real B-rep contour extraction, parallel-3D finishing, waterline finishing,
lathe / turning operations, and a 5-axis path stub. `kerf-cam` exports
`cam.2_5d` (always) plus `cam.parallel-3d`, `cam.waterline`, `cam.lathe`
when pythonOCC is available.

### Topo polish

NURBS-driven STEP reconstruction of optimized geometry, smoothing pass,
and multi-body topology support. `kerf-topo` exports `topo.simp`.

### Mates UI restored

Three.js mate visualisation back in the viewport. BREP face/edge picker
returned; mate authoring is a click+click again. Tolerance auto chain-walk
follows assembly mates through nested sub-assemblies.

### Scalability — S1 + S2

Frustum culling (S1) and `InstancedMesh` batching (S2) for the Three.js
scene. Assemblies with hundreds of identical components now render at
interactive frame rates.

### Performance Phase 4 — revision DB

Real diff-based `file_revisions` with SHA-256 deduplication and a
safe-prune path. ~82× size reduction on a representative corpus. New
`kerf-server revisions repack` subcommand back-fills the new format on
existing rows (idempotent, dry-runnable, prune-on-confirm).

### Planned designs landed in `docs/plans/`

- [FreeCAD sketch → 3D shortcuts](./plans/freecad-sketch-shortcuts.md) —
  `feature_boss_with_draft`, `feature_cut_from_sketch`,
  `feature_hole_pattern_from_sketch`, symmetric loft, corrected-Frenet sweep.
- [Sketch → JSCAD workflow](./plans/sketch-to-jscad.md) — mesh-side analog of
  the `.sketch → .feature` BRep path.

---

## Sprint — earlier in May 2026 (Massive Feature Wave)

### Sketcher / Mechanical
6 new constraints (horizontal/vertical distance, symmetric, block, equal angle, parallel). Arc/circle edge projection for external geometry. Multi-loop holes in extrude/pocket. 3D backdrop overlay. Carbon-copy sketches with validation. (`packages/kerf-chat/llm_docs/sketch.md`)

### Features — PartDesign / FreeCAD Parity
Helix (variable-pitch), tapered Draft, Mirror, Multi-Transform, and Rib features shipped. ~10 new curve operations (offset, extend, blend, trim, intersect, project, section, split, isotrim, swap).

### Surface Modeling — Rhino Parity
SubD (Catmull-Clark subdivision surfaces). Full 3DM import/export. Mesh tools: remesh, decimate, smooth, repair, fill-holes, surface-from-points. Render-quality output via Blender Cycles. Parametric `.graph` (Grasshopper-equivalent).

### Drawings — Draft Workbench
Hatch patterns, leader lines, rich text, and dimension chains — full drafting completeness. Draft workbench (2D CAD) for technical drawings.

### Architecture — Revit Parity
IFC compiler (`POST /compile-ifc` → IFC4 via IfcOpenShell). `.family.json` parametric components, `.schedule.json` query DSL, `.view.json` saved views, `.sheet.json` print layouts. Categories + hosted references, type vs instance params, phasing + view filters. Stairs, railings, MEP routing (`.duct`/`.pipe`/`.conduit`), curtain wall, sheet revisions.

### Electronics — KiCad Parity
Manual trace routing, copper pours/ground planes, full layer stack. PCB DRC, ERC (electrical rules check), net classes. Length tuning + diff-pair match, via stitching + teardrops. Push-pull (shove) router. Hierarchical schematics, buses + differential pairs. Per-pad mask/paste overrides.

### Workshop / Library / Cloud
Workshop + Library endpoints ported into `kerf-cloud`. Cloud git → S3 Storer (stateless serverless). Large-file `.step-ref` Phase 1 (JSON pointer + object storage). GitHub OAuth. AES-GCM encrypt utility.

### Inspection / Misc
Model comparison tool. Distributor catalog ported. Configurable layers + display modes.
