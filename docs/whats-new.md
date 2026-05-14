# What's New

Recent features shipped to Kerf. See [ROADMAP.md](https://github.com/kerf-sh/kerf/blob/main/ROADMAP.md) for the full list and status of every item.

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
