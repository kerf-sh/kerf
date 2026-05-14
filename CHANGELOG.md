# Changelog

All notable changes to Kerf are recorded here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

The authoritative source for what's shipped vs in-flight is
[ROADMAP.md](./ROADMAP.md). This file summarizes each tagged release.

## [Unreleased]

See `🔮 planned` rows in [ROADMAP.md](./ROADMAP.md). The v0.2 milestone
focus is in [docs/plans/v0.2-milestone.md](./docs/plans/v0.2-milestone.md).

## [0.1.0] — 2026-05-15

Initial public release. The core platform across mechanical, electronics,
BIM, drawings, sharing, scripting, and hosting is all in.

### Mechanical CAD

- 2D parametric sketcher (planegcs constraint solver). 6 new constraints
  in v2 (horizontal/vertical distance, symmetric, block, equal angle,
  parallel). Arc/circle external-geometry projection. Carbon-copy
  sketches. Trim, extend, B-spline cubic, fillet, mirror, linear +
  polar pattern. Multi-loop holes.
- OpenCascade `.feature` files: Pad, Pocket, Revolve, Fillet, Chamfer,
  Shell, Hole, Sweep1, Sweep2, Loft, Push-Pull, RotateFace, Linear /
  Polar / Mirror patterns, variable-radius fillet.
- FreeCAD-parity sketch shortcuts: boss-with-draft, cut-from-sketch,
  hole-pattern-from-sketch. Symmetric Loft. Sweep1 corrected-Frenet
  mode.
- Phase 4a NURBS surfacing: `sweep1`, `sweep2`, `network_srf`,
  `blend_srf` with C0/C1/C2 and G0/G1/G2 continuity.
- Phase 4b direct manipulation: face gumball (translate + rotate), edge
  gumball (drag-to-fillet).
- NURBS booleans v1: `feature_to_solid` cap-then-boolean + `feature_boolean`
  (cut / fuse / common) on solids.
- NURBS Phase 4 Capability 1 first 3 tasks: binding probe + worker
  handler + Python tool for surface-direct booleans (with fallback paths
  when OCCT bindings are absent).
- Persistent face naming: sketch-anchored primary +
  topological-hash fallback. Survives upstream sketch edits.
- Sketch → JSCAD workflow: `extrude_sketch_to_jscad` LLM tool +
  reactive re-eval.
- 5-axis CAM v1: constant-tilt finishing + 3+2 indexed.
- Imports: KiCad (Tier 1 + 2 libraries), OpenSCAD, Rhino3DM, FreeCAD
  Tier 1 (`.FCStd` → `.feature` + `.sketch` + `.assembly`).

### CAE — analysis

- **FEM**: FEniCSx primary, CalculiX second solver. Linear-static +
  modal + thermal. Deformed-shape 3D overlay. Multi-material BCs.
- **CAM**: OpenCAMlib 2.5D (face/contour/pocket/drill/profile) + 3D
  parallel + waterline + lathe + 5-axis stub.
- **Topology optimization**: FEniCSx SIMP + Gmsh + NURBS STEP export.
- **Tolerance stack-up**: worst-case / RSS / Monte Carlo with
  automatic chain-walk through assembly mates.

### Electronics — EDA

- **tscircuit-powered** schematic + PCB + 3D board viewers.
- **SPICE simulation** via ngspice (server-side).
- **RF analysis** via scikit-rf (Smith chart, S-parameters, VSWR).
- **FreeRouting autoroute**.
- **Wiring / harness diagrams**: `.wiring` file kind via WireViz YAML
  → SVG.

### Architecture — BIM

- `.bim` text-DSL → IFC4 compiler via IfcOpenShell.
- Revit-parity authoring: families, schedules, views, sheets,
  categories, phasing, view filters, stairs, railings, MEP routing,
  curtain walls.
- web-ifc 3D viewer in `BIMView`.

### Sharing + Library

- **Workshop**: free + public + automatic. Per-project caps (100MB per
  file, 500MB total, 100 files, 10 cover images, 20 publishes/user/mo).
- **Library**: curated parts with verified-publisher accounts and live
  distributor pricing (DigiKey / Mouser / LCSC).
- **BOM**: per-Component pricing, distributor lookup, export.
- **Multi-image gallery** on Workshop projects.
- **Thumbnail capture** for all file kinds (sketch, drawing, BIM, FEM,
  topo, wiring, schematic, PCB, assembly, RF, plus the existing 3D
  feature view).

### Versioning + sync

- File revisions (Cmd+Z, fine-grained undo) with Phase-4 diff-based
  storage + SHA-256 dedup — ~82× shrink on typical edit patterns.
- Cloud git (pygit2 backend) with commits / branches / merge / GitHub
  sync.
- S3-backed bare-repo storer for stateless serverless deploys.

### Billing + pricing

- Free / Studio $9/mo / Pro $29/mo tiers. Enterprise by-arrangement
  (mailto only — no SDR funnel).
- **At-cost LLM pricing.** No markup on tokens. Live model pricing
  fed from the LiteLLM JSON, refreshed daily.
- Wallet top-up via Paystack for overage (USD displayed, ZAR settled).
- Free-tier tokens redeemable only against cheap-tier models
  (Sonnet 4.7, Gemini 3 Flash Preview, DeepSeek, MiniMax).
- Per-API-token daily spend cap (anti-compromise).

### Scripting

- **`kerf-sdk` Python SDK** on PyPI. JSON-RPC over `/v1/rpc`, API-token
  auth, namespaced wrappers for files / equations / configurations /
  revisions / docs.

### Performance

- **S1 + S2**: frustum culling + InstancedMesh batching in Three.js.
  Assemblies with hundreds of identical components render at
  interactive frame rates.
- **STEP pre-tessellation**: server-side worker pre-renders STEP files
  to GLB on upload, idempotent + content-hashed.

### Infrastructure

- **fly.io + Tigris** in production at `kerf.sh`. Primary region JNB
  (Johannesburg), Tigris S3-compatible storage with zero in-fly egress.
- **One-shot deploy** via `./scripts/deploy-fly.sh`: pushes secrets from
  `.env.production`, deploys app + worker apps, applies migrations.
- **Reference configurations** for GCP / AWS / Azure / DigitalOcean in
  `deployment/`.
- **Multi-stage Dockerfile** embeds the compiled Vite SPA in the same
  image as the FastAPI backend — single image, single fly machine.
- **Plugin monorepo**: 20 plugin packages under `packages/kerf-*/`,
  discovered via Python entry points. Six install personas
  (`api-only` / `mech` / `electronics` / `bim` / `full` /
  `compute-only`).

### Docs

- Public `/roadmap` page with filterable shipped/in-flight/next/planned
  grid.
- Per-cloud deployment guides (`deployment/fly.md`, `gcp.md`, `aws.md`,
  `azure.md`, `digitalocean.md`) plus storage-specific companions
  (`tigris.md`, `gcs.md`, `s3.md`, `azure-blob.md`, `spaces.md`).
- Plan-docs for major roadmap items: NURBS booleans v1, NURBS Phase 4
  full breakdown, FreeCAD Tier 1, persistent face naming, 5-axis CAM,
  sketch-to-jscad, FreeCAD sketch shortcuts.

### Known limitations in v0.1.0

- BYO LLM key plumbing is dormant (no UI surface). At-cost pricing
  makes BYO mostly redundant.
- Azure Blob Storage isn't S3-compatible — Azure deployments need a
  MinIO facade or cross-cloud S3. Tracked in
  [docs/plans/](./docs/plans/).
- 5-axis CAM ships T1-T4 (constant-tilt + 3+2 indexed) — full G-code
  emission + tool DB lands in v0.2.
- NURBS Phase 4 ships C1 binding probe + worker + Python tool — full
  surface-direct booleans + trim-by-curve + matchSrf + G3 land
  incrementally.

[Unreleased]: https://github.com/kerf-sh/kerf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kerf-sh/kerf/releases/tag/v0.1.0
