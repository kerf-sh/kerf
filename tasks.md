# Kerf — Task backlog

**[`ROADMAP.md`](./ROADMAP.md) = strategy** (why / what / priority order).
**This file = execution.** Each `### T-<n>` below is sized so a **single
Sonnet agent can complete it in one isolated-worktree run**: bounded scope,
clear target files, a concrete Definition of Done. The autonomous agent loop
pulls from here top-down within a tier.

Status glyphs match the roadmap: `🔴 not started` · `🚧 in flight` ·
`✅ shipped`. Tiers (P0→P3) mirror the roadmap exactly.

**How to add a task:** copy the template, give it the next free `T-<n>`,
place it under the tier that matches its roadmap line, fill every field, and
split anything bigger than ~one agent-run into sequenced sub-tasks with
`Depends-on`. A new uncovered sector → a P3 task + a P3 line in the roadmap.
Keep this file and the roadmap in sync when priorities change.

Template:

```
### T-<n> <title>
- **Priority:** P<0-3>
- **Persona/sector:** <who this unblocks>
- **Status:** 🔴 not started
- **Scope:** <what + why, 2-4 sentences>
- **Target files/packages:** <paths>
- **Definition of Done:** <concrete: tests / criteria>
- **Depends-on:** <T-ids or none>
```

---

## P0 — credibility blockers

### T-1 Sheet metal: flange op + `.feature` schema
- **Priority:** P0
- **Persona/sector:** Mechanical, Automotive (P0-3)
- **Status:** 🔴 not started
- **Scope:** Introduce a `sheet_metal_flange` feature node: base-face +
  edge + flange length + bend angle + bend radius + k-factor. This is the
  primitive every later sheet-metal task composes. No unfold yet — just
  produce correct folded B-rep.
- **Target files/packages:** `src/lib/occtWorker.js` (new `opSheetFlange`
  wired into both `evaluateTree` and `evaluateToFinalShape`),
  `packages/kerf-cad-core/src/kerf_cad_core/` (new `sheet_metal.py` spec +
  `run_*`, register in `_TOOL_MODULES`), `src/components/FeatureView.jsx`
  (inspector entry), `packages/kerf-chat/llm_docs/feature_sheet_metal.md`.
- **Definition of Done:** pytest schema/validation cases (k-factor range,
  angle range, edge ref required) + vitest dispatch cases; LLM doc page;
  inspector entry present. WASM geometry path gated like existing surface ops.
- **Depends-on:** none

### T-2 Sheet metal: bend / unfold solver
- **Priority:** P0
- **Persona/sector:** Mechanical, Automotive (P0-3)
- **Status:** 🔴 not started
- **Scope:** Given a folded sheet-metal body produced by T-1, compute the
  neutral-axis unfold (k-factor / bend-allowance) and produce the unfolded
  flat body. Pure-geometry; the math is the deliverable.
- **Target files/packages:** `src/lib/sheetMetal.js` (pure unfold math +
  bend-allowance helpers), `src/lib/occtWorker.js` (`opSheetUnfold`),
  `packages/kerf-cad-core/src/kerf_cad_core/sheet_metal.py` (unfold spec).
- **Definition of Done:** pure-JS vitest proving bend-allowance against a
  hand-computed reference (90° bend, r=R, t=T, known k); round-trip
  fold→unfold→fold area conservation within tolerance.
- **Depends-on:** T-1

### T-3 Sheet metal: flat-pattern export (DXF stub + 2D outline)
- **Priority:** P0
- **Persona/sector:** Mechanical, Automotive (P0-3)
- **Status:** 🔴 not started
- **Scope:** Emit a `.flatpattern` document (2D polyline outline + bend
  lines + bend-direction annotations) from T-2's unfolded body. Reuse the
  existing `.draft`→DXF-R12 writer path for the DXF export.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  sheet_metal.py`, `src/lib/sheetMetal.js`, a `FlatPatternView.jsx` (SVG,
  pattern after `SectionView.jsx`), migration for the new file kind.
- **Definition of Done:** unfold→flat-pattern produces correct outline +
  bend-line set; DXF export round-trips through the existing R12 writer;
  pytest + vitest.
- **Depends-on:** T-2

### T-4 Sheet metal: bend table + tests
- **Priority:** P0
- **Persona/sector:** Mechanical (P0-3)
- **Status:** 🔴 not started
- **Scope:** Add a per-material/thickness bend-table (`.bendtable` data or
  rows in the material DB) so flange/unfold pick allowance from a table
  rather than a single k-factor. End-to-end integration test.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  sheet_metal.py`, materials DB seed, integration test.
- **Definition of Done:** table lookup overrides scalar k-factor when
  present; integration test fold→unfold→flat with a real bend table.
- **Depends-on:** T-3

### T-5 DWG/DXF: DXF reader (entities → Kerf primitives)
- **Priority:** P0
- **Persona/sector:** Architect, Drafter, Mechanical, Automotive (P0-2)
- **Status:** 🔴 not started
- **Scope:** Pure-Python DXF (R12/2000+) reader: LINE/LWPOLYLINE/CIRCLE/ARC/
  TEXT/INSERT → an intermediate entity model. Read is currently absent
  entirely (only a narrow `.draft`→DXF-R12 *writer* exists).
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/`
  (new `dxf/` package: `reader.py`, `entities.py`).
- **Definition of Done:** parses committed fixture DXFs into the entity
  model; pytest covering each supported entity + an INSERT/BLOCK.
- **Depends-on:** none

### T-6 DWG/DXF: entity map → `.sketch` / `.drawing`
- **Priority:** P0
- **Persona/sector:** Architect, Drafter (P0-2)
- **Status:** 🔴 not started
- **Scope:** Map T-5's entity model onto Kerf's `.sketch` Geom2 (closed
  loops) and `.drawing` (annotations/dimensions) JSON; an `import_dxf` LLM
  tool + pyworker route; FileTree/menu wiring.
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/dxf/`,
  `packages/kerf-imports/src/kerf_imports/tools/import_dxf.py`,
  `src/lib/api.js`, `packages/kerf-imports/llm_docs/import_dxf.md`.
- **Definition of Done:** fixture DXF → valid `.sketch` with closed loops;
  pytest + the standard import-pipeline integration test.
- **Depends-on:** T-5

### T-7 DWG/DXF: general DXF writer (drawings + sketches)
- **Priority:** P0
- **Persona/sector:** Drafter, Mechanical, Automotive (P0-2)
- **Status:** 🔴 not started
- **Scope:** Generalize the existing `.draft`→DXF-R12 writer to export any
  `.drawing` (multi-sheet, dimensions, GD&T frames, hatching) and `.sketch`
  to DXF. This is the supplier-exchange / homologation deliverable.
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/dxf/
  writer.py`, an `export_dxf` LLM tool, doc page.
- **Definition of Done:** `.drawing` with dimensions + GD&T → DXF that
  re-reads through T-5 with entities preserved; pytest round-trip.
- **Depends-on:** T-5

### T-8 DWG/DXF: DWG read via ODA/libredwg bridge (eval)
- **Priority:** P0
- **Persona/sector:** Architect (P0-2)
- **Status:** 🔴 not started
- **Scope:** Spike + implement DWG→DXF conversion via a subprocess bridge
  (libredwg or ODA File Converter), graceful-degradation when the binary is
  absent (same pattern as CuraEngine/Instant-Meshes). Then DWG read reuses
  T-5/T-6.
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/dxf/
  dwg_bridge.py`, route + tool.
- **Definition of Done:** with the binary present, a fixture DWG imports
  via the T-6 path; absent → HTTP 503 + install hint; hermetic test mocks
  the subprocess.
- **Depends-on:** T-6

### T-9 Gerber/fab: RS-274X writer
- **Priority:** P0
- **Persona/sector:** ECAD (P0-1)
- **Status:** 🔴 not started
- **Scope:** CircuitJSON → Gerber RS-274X per copper/mask/silk layer
  (aperture definitions, flashes, draws, polygon pours). This is the single
  biggest credibility blocker for the ECAD persona.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/` (new `gerber.py`), `tools/fab.py` (`export_gerber` LLM tool),
  `packages/kerf-electronics/llm_docs/fab.md`.
- **Definition of Done:** known board → Gerber that parses with a
  third-party Gerber parser in tests (or a hermetic structural assertion);
  per-layer file set; pytest.
- **Depends-on:** none

### T-10 Gerber/fab: Excellon drill writer
- **Priority:** P0
- **Persona/sector:** ECAD (P0-1)
- **Status:** 🔴 not started
- **Scope:** CircuitJSON pad/via holes → Excellon drill file (tool table,
  plated/non-plated, drill hits). Pairs with T-9 in the fab package.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/excellon.py`.
- **Definition of Done:** tool table matches distinct hole sizes; hit count
  equals pad/via count; pytest with a fixture board.
- **Depends-on:** T-9

### T-11 Gerber/fab: pick-and-place + fab BOM
- **Priority:** P0
- **Persona/sector:** ECAD (P0-1)
- **Status:** 🔴 not started
- **Scope:** Centroid/rotation pick-and-place CSV (top/bottom) + fab BOM
  CSV (refdes, value, footprint, distributor). Reuse the existing BOM rollup.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/pnp.py`, `fab_bom.py`.
- **Definition of Done:** P&P rows = placed components with correct
  side/rotation; fab BOM groups by value+footprint; pytest.
- **Depends-on:** T-9

### T-12 Gerber/fab: IPC-2581 / ODB++ + fab zip bundle
- **Priority:** P0
- **Persona/sector:** ECAD (P0-1)
- **Status:** 🔴 not started
- **Scope:** Single `export_fab_package` tool that bundles T-9/T-10/T-11
  outputs + an IPC-2581 XML (ODB++ optional) into one downloadable zip — the
  actual deliverable a fab house ingests.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/ipc2581.py`, `tools/fab.py`, `PCBView.jsx` "Export fab package" button.
- **Definition of Done:** zip contains Gerbers + drill + P&P + BOM +
  IPC-2581; IPC-2581 validates against the schema in a test.
- **Depends-on:** T-9, T-10, T-11

### T-13 Persistent face naming: boolean-heavy regression corpus
- **Priority:** P0
- **Persona/sector:** All / chat-driven core (P0-4)
- **Status:** 🔴 not started
- **Scope:** Build a regression corpus of boolean-heavy `.feature` models
  (cut/fuse/common chains, pattern-then-fillet, sketch-edit-then-reeval) and
  assert face-name stability across re-eval. Hardens the shipped T1–T2.
- **Target files/packages:** `src/__tests__/faceNamingRegression.test.js`,
  fixture `.feature` JSON under `src/__tests__/fixtures/`.
- **Definition of Done:** ≥10 boolean-heavy fixtures; each asserts that a
  named face survives an upstream sketch edit; failures pinpoint the op.
- **Depends-on:** none

### T-14 Persistent face naming: boundary-face naming on booleans
- **Priority:** P0
- **Persona/sector:** All / chat-driven core (P0-4)
- **Status:** 🔴 not started
- **Scope:** Implement deterministic naming for faces *created by* boolean
  ops (the open question in `docs/plans/persistent-face-naming.md`) using
  the OCCT Modified/Generated maps already extracted in T2.
- **Target files/packages:** `src/lib/faceNaming.js`, `src/lib/occtWorker.js`.
- **Definition of Done:** T-13 corpus passes for boolean-boundary faces;
  unit tests for `nameOpOutput` on cut/fuse/common with shared edges.
- **Depends-on:** T-13

### T-15 Large-assembly perf harness + measured ceiling
- **Priority:** P0
- **Persona/sector:** Mechanical, Architect, Automotive (P0-5)
- **Status:** 🔴 not started
- **Scope:** A generator that builds synthetic N-part assemblies (100 →
  10,000) and a harness that measures load + render + interaction time,
  producing a documented ceiling and budget. Defines the problem before
  LOD/lazy-load work.
- **Target files/packages:** `scripts/bench_large_assembly.*`, a results
  doc `docs/plans/large-assembly.md`.
- **Definition of Done:** reproducible numbers at 100/1k/10k parts written
  to the doc; the harness runs in CI-skippable mode.
- **Depends-on:** none

### T-16 Large-assembly: LOD / lazy-load loader
- **Priority:** P0
- **Persona/sector:** Mechanical, Architect, Automotive (P0-5)
- **Status:** 🔴 not started
- **Scope:** Bounding-box/proxy LOD + lazy mesh fetch for assembly
  components beyond a count threshold, driven by the T-15 budget.
- **Target files/packages:** assembly render path in `src/`, `assembly.js`.
- **Definition of Done:** T-15 harness shows the ceiling raised by the
  target factor at 10k parts; vitest for the LOD-selection logic.
- **Depends-on:** T-15

---

## P1 — depth that converts evaluators

### T-20 Jewelry worker op: `opGemstone`
- **Priority:** P1
- **Persona/sector:** Jewelry (P1-2)
- **Status:** 🔴 not started
- **Scope:** Wire the `opGemstone` handler in the OCCT worker so the
  shipped `kerf_cad_core.jewelry.gemstones` node specs render the 7 cuts.
  This is the existing tracked jewelry-render work — split per op so each
  fits one agent run.
- **Target files/packages:** `src/lib/occtWorker.js` (`opGemstone`, wired
  into both evaluators), vitest in `src/__tests__/`.
- **Definition of Done:** gemstone node from `.gem`/`.feature` produces a
  tessellated mesh; round/brilliant facet count assertion; vitest dispatch.
- **Depends-on:** none

### T-21 Jewelry worker op: `opGemSeat`
- **Priority:** P1
- **Persona/sector:** Jewelry (P1-2)
- **Status:** 🔴 not started
- **Scope:** Wire `opGemSeat` (seat/bearing cutter from
  `kerf_cad_core.jewelry.gem_seat`).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** seat node renders; cut-against-shank produces a
  valid solid; vitest.
- **Depends-on:** T-20

### T-22 Jewelry worker ops: prong head + bezel
- **Priority:** P1
- **Persona/sector:** Jewelry (P1-2)
- **Status:** 🔴 not started
- **Scope:** Wire `opJewelryProngHead` and `opJewelryBezel` (from
  `kerf_cad_core.jewelry.settings`).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** both ops render; prong count matches the spec;
  vitest dispatch for each.
- **Depends-on:** T-21

### T-23 Jewelry worker ops: channel + pavé
- **Priority:** P1
- **Persona/sector:** Jewelry (P1-2)
- **Status:** 🔴 not started
- **Scope:** Wire `opJewelryChannel` and `opJewelryPave` (auto-array on a
  surface).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** pavé array places N stones on a target surface;
  channel rail renders; vitest.
- **Depends-on:** T-22

### T-24 Jewelry worker op: `opRingShank` + end-to-end ring
- **Priority:** P1
- **Persona/sector:** Jewelry (P1-2)
- **Status:** 🔴 not started
- **Scope:** Wire `opRingShank` (from `kerf_cad_core.jewelry.ring`, 7 shank
  profiles + sizer) and add an end-to-end test: shank + seat + prongs +
  stone renders as one assembled ring, with metal-cost panel populated.
- **Target files/packages:** `src/lib/occtWorker.js`,
  `src/__tests__/jewelryRingIntegration.test.js` (WASM-gated).
- **Definition of Done:** full ring renders; metal-weight/cost computed;
  WASM-gated integration test.
- **Depends-on:** T-23

### T-25 Weldments: structural member op
- **Priority:** P1
- **Persona/sector:** Mechanical (P1-3)
- **Status:** 🔴 not started
- **Scope:** `weldment_member` feature: a profile (from a standard-section
  table) swept along selected sketch path segments, with trim-at-joint.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  weldment.py`, `src/lib/occtWorker.js` (`opWeldmentMember`), FeatureView,
  doc page.
- **Definition of Done:** members along a 3-segment path with mitred
  joints; pytest schema + vitest dispatch.
- **Depends-on:** none

### T-26 Weldments: cut list
- **Priority:** P1
- **Persona/sector:** Mechanical (P1-3)
- **Status:** 🔴 not started
- **Scope:** Roll up weldment members into a cut list (profile, length,
  qty, angle) reusing the BOM rollup pattern.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  weldment.py`, a cut-list view.
- **Definition of Done:** cut list groups identical members; CSV export;
  pytest.
- **Depends-on:** T-25

### T-27 GD&T-from-model: model-driven datum + tolerance callouts
- **Priority:** P1
- **Persona/sector:** Mechanical, Automotive (P1-3)
- **Status:** 🔴 not started
- **Scope:** Attach datums + geometric tolerances to model faces/edges and
  have the drawing engine place the GD&T frame automatically on projected
  views (frames already render; the model→callout link is the gap).
- **Target files/packages:** `.feature` schema (datum/tolerance slots),
  drawing projection code, LLM tool + doc.
- **Definition of Done:** a toleranced model face produces a positioned
  GD&T frame on its drawing view; pytest + vitest.
- **Depends-on:** none

### T-28 IFC import Tier 2: openings + MEP
- **Priority:** P1
- **Persona/sector:** Architect (P1-4)
- **Status:** 🔴 not started
- **Scope:** Extend `kerf_bim.import_ifc` (Tier 1 today) to parse
  `IfcOpeningElement` (windows/doors) and `IfcDistributionElement` (MEP)
  into `.bim` JSON.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/import_ifc/`
  (new `openings.py`, `mep.py`), parser wiring.
- **Definition of Done:** fixture IFC with openings + MEP imports
  correctly; hermetic-mock pytest like the Tier-1 suite.
- **Depends-on:** none

### T-29 IFC import Tier 2: families + schedules + views
- **Priority:** P1
- **Persona/sector:** Architect (P1-4)
- **Status:** 🔴 not started
- **Scope:** Parse IFC type objects → `.family.json`, quantity sets →
  `.schedule.json`, plan/section context → `.view.json`.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/import_ifc/`
  (`families.py`, `schedules.py`).
- **Definition of Done:** fixture IFC produces valid family/schedule JSON;
  pytest.
- **Depends-on:** T-28

### T-30 Parametric family editor (Revit moat)
- **Priority:** P1
- **Persona/sector:** Architect (P1-4)
- **Status:** 🔴 not started
- **Scope:** A `.family.json`-authoring flow where parameters drive nested
  geometry (extends the shipped `.family` data model into a true parametric
  editor with constraints + flex test).
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/tools/
  family.py`, `src/lib/family.js`, editor.
- **Definition of Done:** a parametric column family flexes correctly
  across parameter sets; pytest + vitest "flex" test.
- **Depends-on:** none

### T-31 ECAD: 3D board STEP export
- **Priority:** P1
- **Persona/sector:** ECAD (P1-1)
- **Status:** 🔴 not started
- **Scope:** CircuitJSON board + component 3D models → a STEP assembly for
  MCAD-ECAD co-design (the cross-project PCB-as-part path consumes it).
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  ` (new `board_step.py`), tool + doc.
- **Definition of Done:** board outline + placed component STEPs export as
  one STEP that reloads; pytest (OCC-gated).
- **Depends-on:** none

### T-32 kerf-parts: complete bolts adapter
- **Priority:** P1
- **Persona/sector:** Mechanical / ECAD ecosystem (P1-1)
- **Status:** 🔴 not started
- **Scope:** Finish the scaffold-stage BOLTS adapter
  (`adapters/bolts.py`) so BOLTS fasteners convert into native library
  parts through the MIT-clean fetch/convert pipeline.
- **Target files/packages:** `packages/kerf-parts/src/kerf_parts/adapters/
  bolts.py`, tests.
- **Definition of Done:** a pinned BOLTS fixture converts to ≥1 valid
  `kind='part'` file with provenance; pytest (no committed third-party data).
- **Depends-on:** none

### T-33 kerf-parts: complete freecad-library adapter
- **Priority:** P1
- **Persona/sector:** Mechanical ecosystem (P1-1)
- **Status:** 🔴 not started
- **Scope:** Finish the scaffold-stage FreeCAD-library adapter
  (`adapters/freecad_library.py`).
- **Target files/packages:** `packages/kerf-parts/src/kerf_parts/adapters/
  freecad_library.py`, tests.
- **Definition of Done:** a pinned fixture converts to valid native parts;
  pytest.
- **Depends-on:** none

### T-34 kerf-partsgen: author standard fastener families
- **Priority:** P1
- **Persona/sector:** Mechanical ecosystem (P1-1)
- **Status:** 🔴 not started
- **Scope:** Add parametric generators for the next standard families
  (ISO 4762 socket-head cap screw, ISO 4032 hex nut, DIN 125 washer) using
  the author-once-then-enumerate framework. One family per agent run.
- **Target files/packages:** `packages/kerf-partsgen/src/kerf_partsgen/
  generators/`, `verify.py` fixtures.
- **Definition of Done:** each generator enumerates its full SIZES table
  deterministically (zero tokens) and passes `verify.py` geometry checks.
- **Depends-on:** none

### T-35 Class-A: zebra / reflection-line analysis (the shippable slice)
- **Priority:** P1
- **Persona/sector:** Automotive (P1-6)
- **Status:** 🔴 not started
- **Scope:** Environment-map / stripe shader on the tessellated NURBS
  surface in the existing Three.js viewport — the cheap, no-WASM Class-A
  credibility win called out in `docs/plans/automotive.md`. **Does not**
  attempt algorithmic G3 (deferred custom-WASM moat).
- **Target files/packages:** Three.js surface render path in `src/`, a
  `ZebraOverlay`-style component + toggle, LLM doc.
- **Definition of Done:** zebra/reflection stripes render on a blend
  surface with a continuity-band toggle; vitest for the shader-param math;
  no OCCT/WASM dependency.
- **Depends-on:** none

### T-36 3D wiring harness: route-through-DMU primitive
- **Priority:** P1
- **Persona/sector:** Automotive, ECAD (P1-7)
- **Status:** 🔴 not started
- **Scope:** A `harness_segment` op that routes a bundle along a 3D path
  with diameter from a wire list — the primitive 3D harness needs (today
  only 2D WireViz exists). Formboard flatten + voltage-drop are later tasks.
- **Target files/packages:** `packages/kerf-wiring/src/kerf_wiring/` (new
  3D module), `src/lib/occtWorker.js` (sweep-based bundle), doc.
- **Definition of Done:** a bundle routes along a 3-point path with correct
  diameter; length computed; pytest + vitest.
- **Depends-on:** none

### T-37 Surface-boolean robustness on dense NURBS
- **Priority:** P1
- **Persona/sector:** Jewelry, Automotive (P1-5)
- **Status:** 🔴 not started
- **Scope:** Eliminate runtime escalation paths in `opSurfaceBoolean` so
  dense organic NURBS survive booleans reliably (fuzzy-value tuning,
  ShapeFix pre-pass strategy, deterministic fallback ordering).
- **Target files/packages:** `src/lib/occtWorker.js` (`opSurfaceBoolean`),
  `src/lib/occtBridge.js`, WASM-gated integration tests.
- **Definition of Done:** a dense-NURBS boolean corpus passes without the
  C1-T10 escalation; WASM-gated integration test green in CI.
- **Depends-on:** none

---

## P2 — moats / breadth (representative starters)

### T-50 FEM: nonlinear material (plasticity) path
- **Priority:** P2
- **Persona/sector:** Mechanical, Automotive (P2 sim)
- **Status:** 🔴 not started
- **Scope:** Add a nonlinear (J2 plasticity) `analysis_type` to the FEM
  solver (today the verified enum is `linear_static | modal | thermal`
  only). First step of the broader nonlinear/crash/fatigue line.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/` (solver +
  `tools.py` enum), tests (analytical cantilever-yield reference).
- **Definition of Done:** nonlinear run matches an analytical
  elastic-plastic reference within tolerance; engine-absent → sentinel.
- **Depends-on:** none

### T-51 Clash detection across disciplines
- **Priority:** P2
- **Persona/sector:** Architect, Mechanical (P2)
- **Status:** 🔴 not started
- **Scope:** Pairwise interference check across assembly components /
  IFC elements, producing a clash report.
- **Target files/packages:** new module + LLM tool + report view.
- **Definition of Done:** known-overlapping fixture yields the expected
  clash set; pytest.
- **Depends-on:** none

### T-52 Scan-to-CAD: point-cloud ingest + primitive fit
- **Priority:** P2
- **Persona/sector:** Reverse engineering (cross-cutting, P2)
- **Status:** 🔴 not started
- **Scope:** Ingest a point cloud (PLY/E57 subset) and fit basic
  primitives (plane/cylinder/sphere) — the high-leverage reverse-engineering
  seed.
- **Target files/packages:** new import package + tool + viewer.
- **Definition of Done:** synthetic cloud → correct fitted primitives
  within tolerance; pytest.
- **Depends-on:** none

### T-53 Nesting / cut-optimization for sheet/laser
- **Priority:** P2
- **Persona/sector:** Fabrication (P2)
- **Status:** 🔴 not started
- **Scope:** 2D part nesting (bin-packing with rotation) for laser/waterjet
  cut sheets; consumes sheet-metal flat patterns.
- **Target files/packages:** new module + tool + layout view.
- **Definition of Done:** a part set nests within a sheet with measured
  utilization; pytest on the packing math.
- **Depends-on:** T-3

---

## P3 — long-tail verticals (representative starters)

P3 is the proof that "we do everything." Do not enumerate the whole tail
here — add tasks as a sector is picked up. Each P3 task also gets/uses a P3
line in the roadmap. Two representative seeds:

### T-70 Civil engine seed: geospatial CRS + TIN terrain
- **Priority:** P3
- **Persona/sector:** Civil (P3 — distinct engine)
- **Status:** 🔴 not started
- **Scope:** The foundational *distinct* civil engine: a coordinate
  reference system module (EPSG transform via pyproj) + a TIN terrain model
  from survey points with contour extraction. Civil is **not** a feature-add
  on the B-rep kernel — this task stands up its own engine seed.
- **Target files/packages:** new `packages/kerf-civil/` (or module) — `crs.py`,
  `tin.py`; LLM tool + doc.
- **Definition of Done:** survey-point fixture → triangulated TIN +
  contour lines at a given interval; CRS transform round-trips a known
  point; pytest.
- **Depends-on:** none

### T-71 Marine: NURBS hull-fairing seed
- **Priority:** P3
- **Persona/sector:** Marine / naval architecture (P3 — NURBS-reachable)
- **Status:** 🔴 not started
- **Scope:** A hull-surface fairing helper that builds a lofted hull from
  station offsets and reports fairness via the existing curvature-comb
  infra — close to Kerf's NURBS strength, hence a good early P3 pick.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/`
  (hull helper reusing `surfacing.py`), doc.
- **Definition of Done:** offset table → faired hull surface; curvature
  combs render on it; pytest schema + vitest dispatch.
- **Depends-on:** none
