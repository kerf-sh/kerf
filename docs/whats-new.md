# What's New

Recent features shipped to Kerf. See [ROADMAP.md](https://github.com/imranp/kerf/blob/main/ROADMAP.md) for the full list and status of every item.

## Sprint — May 2026

### Architecture: IFC + text-DSL
New `.bim` project type. Write buildings in a readable DSL (`level`, `wall`, `slab`, `space`, `opening`) or JSON. pyworker `POST /compile-ifc` compiles to IFC4 via IfcOpenShell. Viewer uses web-ifc + Three.js (`BIMView.jsx`). Backend tools: `create_bim`, `read_bim`, `compile_bim_to_ifc`, `read_ifc`. IfcOpenShell import is try/except gated.

### Docs restructure
This page. Added `docs/index.md` TOC, `docs/whats-new.md` sprint summary, and wired both into the docs SPA manifest. Eight stale ROADMAP labels updated.

### Sketcher v2 — complete
6 new constraints: horizontal distance, vertical distance, symmetric, block, equal angle, parallel lines. Arc/circle edge projection for external geometry. Multi-loop holes in extrude pockets. 3D backdrop overlay. All vitest passing.

### Materials database — 55 materials
Expanded from 20 to 55 curated engineering materials covering metals, polymers, composites, ceramics, and electronics substrates. Consumed by FEM, tolerance analysis, Part defaults, and drawing callouts.

### Cross-project parts — Phase 3 complete
`bulk_refresh` endpoint refreshes all external component refs in one call. `lock_assembly` + lockfile pattern pins the assembly to known-good ref versions. Diff tooltip surfaces what changed when an external component is out of date.

### Import: OpenSCAD (shipped)
Browser-side parser (no pyworker dep) translates OpenSCAD to `.jscad` source, preserving the parametric model. 18 vitest tests passing. Escape hatch for exotic features runs the OpenSCAD binary as a subprocess.

### Import: KiCad (Tier 1 shipped)
`/import-kicad` pyworker route parses `.kicad_sch` and `.kicad_pcb` to `.circuit.tsx` first-cut. LLM tool `import_kicad` wired. File-tree ingest wired. Tier 2 (symbol/footprint libraries) in progress.

### STEP pre-tessellation (in flight)
`auto_tess_worker` running in cloud pyworker with PG LISTEN/NOTIFY. Mesh artifacts stored in `derived_artifacts`. Cloud-tier only — OSS local-install path stays browser-side.

### Cloud git — S3 Storer (shipped)
`S3GitStorer` pluggable go-git Storer backed by R2/S3. Stateless serverless deploys — no local disk required. moto integration tests passing.

### Large-file .step-ref Phase 1 (shipped)
Migration `033_step_ref_kind.sql`. Files >= 5 MB committed as a small JSON pointer content-addressed into object storage. Git history stays lean.
