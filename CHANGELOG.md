# Changelog

All notable changes to Kerf are recorded here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

The authoritative source for what's shipped vs in-flight is
[ROADMAP.md](./ROADMAP.md). This file summarizes each tagged release.

## [Unreleased]

See `🔮 planned` rows in [ROADMAP.md](./ROADMAP.md). The v0.2 milestone
focus is in [docs/plans/v0.2-milestone.md](./docs/plans/v0.2-milestone.md).

### 2026-05-17 (later) — Compare hub matrices, scroll-to-top, CFD foundation, FEM ref-values

Same date as the geometry-kernel step-change below; a second wave of
landings followed in the same window. Captured here as a sibling section
so the kernel + earlier-day entries stay self-contained.

- **Compare hub redesign with per-category feature matrices** —
  `src/routes/compare/index.jsx` + `src/routes/compare/CategoryMatrix.jsx`
  now render Mechanical / Electronic / BIM / Jewelry & NURBS / DCC
  matrices plus per-CAD cards (5 mech + 2 each electronic / BIM /
  jewelry / DCC + 1 drafting). 14 head-to-head comparison routes live
  under `/compare/` (Altium, Autocad, Blender, Civil3d, Freecad, Fusion,
  Inventor, KiCad, MatrixGold, Max3ds, Onshape, Revit, Rhino,
  Solidworks).
- **5 new compare pages wired** — Solidworks / Autocad / Civil3d /
  Inventor / Max3ds (`3736e98` + `5282b3f`), each lazy-loaded via
  `src/App.jsx`.
- **Scroll-to-top on route change** — `src/components/ScrollToTop.jsx`
  wired in `src/App.jsx` (no more landing on `/compare` mid-scroll).
- **Roadmap link in public Header** — `NAV_LINKS` in
  `src/components/Header.jsx` now exposes `/roadmap` alongside Docs and
  Compare.
- **Blender/Cycles render architecture surfaced** — ROADMAP G-7 +
  Roadmap.jsx + Landing.jsx now name the backend-Cycles + browser-path-
  tracer split; T-106 epic split into T-106a..f in `tasks.md` (scene
  translator + materials mapping, Cycles worker, hero-render UX,
  pricing meter, self-host docker, in-browser
  `three-gpu-pathtracer` fallback).
- **Footer + h-scroll defensive guard** — `body { max-width: 100vw }` +
  `overflow-x: clip` on html / body / `#root` in `src/index.css`
  (`bba65ff` / `b2d2689`); Landing.jsx hero wrapper now clips
  defensively for Safari/WebKit.
- **CFD foundation (2-D laminar scope)** — `packages/kerf-fem/src/
  kerf_fem/cfd_potential.py` (potential flow, `Cp(θ) = 1 − 4 sin²θ`
  analytic oracle) + `cfd_navier_stokes.py` (lid-driven cavity,
  Ghia Re=100 reference); 61 hermetic CFD tests in
  `packages/kerf-fem/tests/test_cfd.py`. T-101 stays 🚧 in flight (full
  CfdOF parity = turbulence k-ε / k-ω SST, 3-D unstructured meshing,
  OpenFOAM bridge).
- **FEM reference-value suite** — `packages/kerf-fem/src/kerf_fem/
  pressure_load.py` + 43-test `test_fem_refvalues.py` with citable
  Roark / Blevins / Incropera oracles; 42 green; one ASTM E1049
  rainflow test skipped — real bug flagged in
  `fatigue_fem._rainflow`, tracked under T-100.
- **Test count** — full repo collects **24 134 tests** via
  `pytest --collect-only -q -p no:cacheprovider --no-header` (verified
  this session, +232 over the previous 23 902 baseline).

### 2026-05-17 — Geometry kernel step-change + ship-gate landed

Pure-Python B-rep/NURBS kernel jumped from *Rhino-width construction
verbs, no topology binding, no closest-point, sampling-grade SSI, every
boolean delegated to OCCT* to a real math-depth moat. All in
`packages/kerf-cad-core/src/kerf_cad_core/geom/`.

- **B-rep topology keystone wired** — `brep.py` (1 312 LOC) +
  `brep_build.py` (833 LOC). The frozen `BREP_CONTRACT.md` model
  (`Body → Solid → Shell → Face → Loop → Coedge → Edge → Vertex`, nine
  Euler operators, generalised Euler–Poincaré invariant) now guards
  real geometry: every analytic-verb builder ends with `validate_body`.
- **Tolerant pure-Python solid booleans** — `sew.py` (386 LOC) +
  `boolean.py` (1 195 LOC). Face-imprint via SSI, regularised
  cut / fuse / common over the analytic primitive matrix, tolerance-
  monotonic merge, `validate_body`-clean 2-manifold result with no OCCT.
- **Parametric history DAG with persistent face/edge naming** — new
  `geom/history/` (1 962 LOC). Three-part
  `feature_id::role::fingerprint` selectors survive parameter edits —
  a downstream fillet still targets the *semantically same* edge after
  its upstream box is resized. Evaluators wired for box / cylinder /
  sphere / boolean / chamfer / fillet.
- **G1 / G2 surface fillet + edge chamfer that trim + sew** —
  `fillet_solid.py` (1 631 LOC) + `chamfer.py` (1 040 LOC). G2
  cross-sections, verified curvature continuity, planar+planar and
  planar+cylindrical edge contracts.
- **Surface / curve / loop offsets with exact-distance oracles** —
  `offset.py` (877 LOC). Concentric circle, parallel plane, sphere
  r → r+d analytic oracles.
- **Coons patches** — `coons.py` (519 LOC). Boundary interpolation
  exact to `1e-12`.
- **Closest-point / point-inversion** — `inversion.py` (629 LOC).
  Piegl 6.1 with analytic first + second partials on rational
  surfaces. The foundational primitive snapping/projection/deviation/
  SSI seeding/fitting/draft analysis builds on.
- **Hardened SSI** — `intersection.py` rebuilt with loop-detection,
  tangential-branch detection, small-loop guard, analytic line/quadric
  specialisations. **Rational-weight bug fixed** along the way.
- **FCC Part 15 Class B EMC reference-distance fix** — emc wizard
  limits were ~10.46 dB too low against the published Class B mask;
  corrected at the reference-distance derivation (commit ca9e651).
- **Conftest plugin-name collision fix** — empty
  `tests/__init__.py` files in billing / pricing / plc were blocking
  whole-suite collection; removed (commit e663c64).
- **Python 3.13 asyncio compat** — restored pre-3.10
  `asyncio.get_event_loop()` semantics in the test process so the
  ship-gate runs on 3.13 (commit 775b178).
- **Ship-gate suite — 1 649 fail → 0 fail.** Full repo collection:
  **23 902 tests**. Of these the listed kernel ship-gate files —
  `test_brep_topology` (51), `test_euler_invariants` (63),
  `test_brep_build` (43), `test_boolean_solid` (36), `test_chamfer`
  (30), `test_fillet_blend_g2` (53), `test_offset` (33), `test_coons`
  (49), `test_surface_analysis_refvalues` (46), `test_nurbs_correctness`
  (44), `test_inversion` (42), `test_ssi_robust` (37),
  `test_curve_toolkit_exact` (46), `test_history_dag` (47) — total
  **620 hermetic analytic-oracle-asserted tests**, all green. Counts
  verified via `pytest --collect-only`, not estimated.

Plan + per-task `GK-NN` checklist (P2 interop is next):
[`docs/plans/geometry-kernel-roadmap.md`](./docs/plans/geometry-kernel-roadmap.md).

### 2026-05-17 — Renderer hero / docs viewer / comparison expansion / boot loader

Same date, separate workstreams that landed in the same window as the kernel
step-change above. Tracked here as a sibling section so the kernel entry
stays self-contained.

- **Renderer hero / PBR upgrade** — `captureHeroShot` (`src/lib/heroShot.js`)
  now renders at 2048×2048 with 4× supersampling, ACES tonemapping, a
  PMREM-pre-filtered RoomEnvironment HDRI, and `UnrealBloomPass`; wired into
  `src/components/Renderer.jsx` so Workshop covers, share-cards, and the
  primary 3D viewport share one production-grade lighting path.
- **Frontend touch + responsive polish** — T-C1/T-C2 touch in Renderer,
  T-C3 Gumball touch, T-L1/T-L2 Editor responsive + top-bar overflow,
  T-H2 Docs mobile drawer.
- **Pre-React boot loader** — `src/components/Loader.jsx` +
  `src/components/RouteFallback.jsx` + a pre-React-mount Kerf-branded SVG
  triangles loader injected in `index.html` (no more blank screen on first
  paint).
- **Docs viewer redesign** — grouped sidebar (`domains` + workflows + cloud
  + reference + develop groups) with breadcrumbs, TOC, audit-filter, and
  internal-planning-artifact filtering; `scripts/build-docs-manifest.mjs`
  emits the grouped taxonomy into `public/docs-manifest.json`.
- **Comparison pages expanded** — `src/routes/compare/` now ships
  Altium, Blender, Freecad, Fusion, KiCad, MatrixGold, Onshape, Revit,
  Rhino; the existing Freecad/Kicad/Rhino/Revit/Fusion pages were
  deepened, and Altium/MatrixGold/Blender/Onshape are new this session.
- **Documentation expansion** — ~75 new per-package `llm_docs/` pages
  across kerf-cad-core, kerf-electronics, kerf-imports, kerf-fem,
  kerf-mates, kerf-{cloud,billing,pricing}, kerf-{workers,parts,partsgen,
  cam,topo}, kerf-{core,auth,api}; 17 new user-facing pages under `docs/`
  (`getting-started`, `local-install`, `local-self-host`, `cloud-features`,
  `projects`, `sharing`, `workshop`, `github-sync`, `billing-and-credits`,
  `account-and-auth`, `file-revisions`, `persona-bundles`,
  `plugins-development`, `configuration`, `deployment`, `llm-tool-authoring`,
  `sdk`, `api-reference`, `data-model`, `tool-registry`, `contributing`,
  `troubleshooting`, and the three vertical workflow guides:
  `jewelry-workflow`, `mechanical-workflow`, `electronic-workflow`).
- **Cross-vertical e2e tests** — 57 cross-vertical parametric e2e tests
  spanning jewelry / mechanical / electronic workflows, in addition to
  the 620 kernel ship-gate tests. Full repo total ~23 902, all green.

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
