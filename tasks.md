# Kerf — Task backlog (money/reach-prioritized)

**[`ROADMAP.md`](./ROADMAP.md) = strategy** (why / what / priority order).
**This file = execution.** Each `### T-<n>` below is sized so a **single
Sonnet agent can complete it in one isolated-worktree run**: bounded scope,
clear target files, a concrete Definition of Done.

## The prioritization lens

The roadmap orders by *leverage / credibility per unit work*. This backlog
re-orders the **same committed work** by a sharper, money-and-reach lens so
the autonomous Sonnet loop always pulls the highest-value task next:

> **rank ≈ (people covered) × (sectors covered) × (revenue / willingness-to-pay) ÷ effort**

Two tiers drive the ranking:

- **Tier A — persona unlock (revenue).** Flips a *whole persona* from
  "cannot ship their deliverable" → "can". Clearest willingness-to-pay: a
  professional who literally cannot deliver without it will pay for it.
- **Tier B — cross-sector multiplier (reach / funnel).** Helps *every*
  sector at once and grows the top of funnel (more evaluators, lower
  cold-start, stronger conversion surface).

Within a tier, ties break on **effort** (cheaper-and-already-mostly-built
wins) and **P-tier** (the roadmap's leverage order).

Status glyphs match the roadmap: `🔴 not started` · `🚧 in flight` ·
`✅ shipped`. **Priority** (P0–P3) on each task mirrors the roadmap exactly;
**Tier** (A/B) is the money/reach classification used for ordering.

---

## Execution order (money/reach-ranked) — pull top-down

This ordered list is **authoritative**. The detailed task bodies are grouped
by tier below for reference, but the agent loop pulls in *this* sequence.

| # | Task | Tier | Money/reach justification (people × sectors × revenue ÷ effort) |
|---|---|---|---|
| 1 | **T-9** Gerber RS-274X writer | A | First step that starts flipping the **electronic engineer** persona from 🔴 *cannot manufacture* → can. ECAD is a P0 spine persona with a large, paying professional workforce; design side is already KiCad-class so this single output unlocks all of it. Highest revenue-per-effort: one persona, hard willingness-to-pay (no fab = no product). |
| 2 | **T-10** Excellon drill writer | A | Completes the second mandatory fab artifact for the same ECAD persona. Cheap (pairs with T-9 in the same package) and a hard gate — a board with no drill file is unmanufacturable. |
| 3 | **T-11** Pick-and-place + fab BOM | A | Third fab artifact; assembly houses require P&P + fab BOM. Reuses the shipped BOM rollup → low effort, same high-value persona. |
| 4 | **T-12** IPC-2581 / ODB++ + fab zip bundle | A | The *actual* deliverable a fab house ingests — this is the moment the ECAD persona crosses 🔴→✅. Completes the single biggest P0 credibility blocker; large paying persona fully unlocked. |
| 5 | **T-20**→**T-24** Jewelry worker ops (`opGemstone`…`opRingShank`, end-to-end ring) | A | Flips the **jewelry CAD** persona from "shipped-but-dead" → usable. Build cost is *already paid* (Python toolkit + UI + `.gem` migration all shipped); only the JS worker wiring remains → extraordinary revenue-per-effort. High-margin niche, distinct paying segment. Sequenced 5a–5e. |
| 6 | **T-5** DXF reader | A | First step of the **one feature that unlocks THREE personas at once** — drafter + architect + automotive (DWG/DXF is the linchpin for all three; only a narrow `.draft`→DXF-R12 writer exists). 3 big paying personas × 1 feature = top reach-weighted revenue. |
| 7 | **T-6** DXF entity-map → `.sketch`/`.drawing` | A | Makes the DXF read path actually usable (drafter + architect can *open* industry files). Completes the inbound half of the 3-persona unlock. |
| 8 | **T-7** General DXF writer | A | The supplier-exchange / homologation deliverable for drafter + mechanical + automotive — outbound half of the 3-persona unlock; generalizes existing R12 writer (lower effort than from-zero). |
| 9 | **T-50' / T-NEW-PRIV** Paid-tier private-by-default | A | Classic paid conversion lever: privacy. Touches *every* cloud persona's willingness-to-pay (private projects is the #1 reason hobbyists upgrade). Tiny, isolated change keyed off billing buckets → very high revenue-per-effort. Self-hosted N/A. |
| 10 | **T-1**→**T-4** Sheet metal (flange→unfold→flat-pattern→bend-table) | A | Biggest single mechanical sub-need and BIW stamping for **automotive** — two large paying personas. Bigger effort (4 sequenced sub-tasks) so it ranks just below the cheaper persona-unlocks, but it is a hard P0 mechanical/automotive credibility gap. Sequenced 10a–10d. |
| 11 | **T-8** DWG read via ODA/libredwg bridge | A | Extends the 3-persona DXF unlock to true **DWG** (architecture/automotive run on DWG, not just DXF). Depends on the DXF path; bridge-eval effort, hence after the cheaper wins. |
| 12 | **T-40**→**T-45** Workshop README workstream (schema → AI-gen → cover → public page → publish UX → tests) | B | Repositions Workshop from Thingiverse image-gallery → **GitHub-for-parametric-CAD**: every published project becomes a discoverable, forkable, AI-documented asset. Single biggest top-of-funnel multiplier across *all* sectors simultaneously; compounds SEO + fork conversion. Sequenced 12a–12f. |
| 13 | **T-46** KiCad parts seed via `kerf-parts` | B | Populates the just-built parts pipeline for **electronics** (huge) — turns an empty library into a cold-start killer for the same large ECAD persona just unlocked by fab output. Reach + funnel across electronics. |
| 14 | **T-34** kerf-partsgen: standard fastener families | B | Populates the mechanical side of the library (author-once-then-enumerate) — cold-start killer across **all mechanical** sectors; zero-token enumeration → cheap, broad reach. |
| 15 | **T-47** Jewelry generated-parts render check | B | Closes the parts-library loop for **jewelry** (depends on jewelry worker-ops) — ensures the now-usable jewelry niche also has a populated, renderable library. |
| 16 | **T-48** Education / maker on-ramp | B | Biggest *raw reach* + mission (ROADMAP §2): polished simple-parametric + cut-list/flat-pack path + on-ramp; slicing + CAM already shipped. Grows the widest possible top-of-funnel for the smallest incremental effort. |
| 17 | **T-13**→**T-14** Persistent face-naming boolean hardening | A | Protects *every* persona's revenue: a topo-naming failure under booleans breaks the product for everyone. Not a new unlock (hence not top), but a high-leverage correctness moat across all sectors. Sequenced 17a–17b. |
| 18 | **T-15**→**T-16** Large-assembly perf (harness → LOD/lazy-load) | A | Unblocks mechanical + architect + automotive at scale (1000s–10,000s of parts; full-vehicle DMU). Cross-persona; harness-first defines the budget before the loader. Sequenced 18a–18b. |
| 19 | **T-31** ECAD 3D board STEP export | A | Deepens the freshly-unlocked ECAD persona into MCAD-ECAD co-design (the cross-project PCB-as-part path consumes it) — extends revenue from a persona already converting. |
| 20 | **T-37** Surface-boolean robustness on dense NURBS | A | Reliability moat for **jewelry + automotive** organic models — protects the jewelry revenue just unlocked and the Class-A automotive path. |
| 21 | **T-35** Class-A zebra / reflection-line slice | A | The cheap, no-WASM Class-A credibility win for **automotive** — visible quality signal that converts automotive evaluators; low effort (shader-side). |
| 22 | **T-25**→**T-26** Weldments (member → cut list) | A | Converts the **mechanical** persona deeper (structural fabrication + cut list). Sequenced 22a–22b. |
| 23 | **T-27** GD&T-from-model callouts | A | Mechanical + automotive correctness/standards depth (frames already render; model→callout link is the gap) — standards features are *more* important under an LLM. |
| 24 | **T-28**→**T-29** IFC import Tier 2 (openings/MEP → families/schedules) | A | Deepens the **architect** persona (interop with the real BIM ecosystem). Sequenced 24a–24b. |
| 25 | **T-30** Parametric family editor (Revit moat) | A | Architect-persona depth + a recognized competitive moat. |
| 26 | **T-32** kerf-parts: complete bolts adapter | B | Further populates the mechanical/ECAD parts ecosystem (scaffold-stage adapter → working). Reach multiplier. |
| 27 | **T-33** kerf-parts: complete freecad-library adapter | B | Same parts-ecosystem reach multiplier for the mechanical side. |
| 28 | **T-36** 3D wiring harness route-through-DMU primitive | A | Automotive + ECAD depth (today only 2D WireViz) — opens a new deliverable for two personas already on the path. |
| 29 | **T-50** FEM nonlinear (plasticity) path | A | First step of the broad simulation pillar (mechanical + automotive); P2 — moat depth, not a P0 unlock, hence ranked here. |
| 30 | **T-51** Cross-discipline clash detection | B | Cross-sector (architect + mechanical) platform multiplier; P2. |
| 31 | **T-52** Scan-to-CAD point-cloud + primitive fit | B | High-leverage cross-cutting reverse-engineering seed (mechanical/architecture/automotive/medical); P2. |
| 32 | **T-53** Nesting / cut-optimization for sheet/laser | B | Cross-sector fabrication multiplier; consumes sheet-metal flat patterns; P2. |
| 33 | **T-70** Civil engine seed (CRS + TIN terrain) | B | Highest raw societal importance, engine-gated → P3; proof-of-"we do everything" seed. |
| 34 | **T-71** Marine NURBS hull-fairing seed | B | NURBS-reachable long-tail vertical; P3 proof seed. |
| 35 | **T-100** FEM matching CalculiX / Z88 / Mystran depth | A | Mechanical + automotive simulation depth (2 personas, P2). Seed nonlinear / explicit / acoustics / EM / fatigue modules already in `kerf-fem`; needs wiring through the public analysis enum + reference-tool match. Hardening stream is in flight in parallel. |
| 36 | **T-104** Kernel G3 + NURBS Phase 4 trim-by-curve + class-A leading | A | Automotive + jewelry Class-A surface depth. G3 curvature combs partially shipped (#100); imprint (GK-19) + class-A leading remain. Kernel-side depth → opus-spine. |
| 37 | **T-101** CFD CfdOF-class — turbulence + 3-D meshing + OpenFOAM bridge | A | Mechanical + automotive + aerospace depth. `cfd_potential.py` seed in flight; full CfdOF parity is engine-class. |
| 38 | **T-109** BIM parametric family-authoring UX | A | Architect-persona depth (Tier-2 family *import* shipped; native authoring is the gap). Revit's signature capability — strong conversion lever for the architect segment. |
| 39 | **T-111** BIM walls / doors / windows / slabs full parametric | A | Same architect-persona depth; today basic primitives, need full Revit-equivalent parametric envelope objects. |
| 40 | **T-112** BIM stairs / ramps full | A | Same architect-persona depth; basic stairs shipped, full Revit-class stair/ramp authoring needed. |
| 41 | **T-110** BIM family library | A | Architect-persona depth: a populated parametric-family catalog (cold-start killer once T-109 lands). |
| 42 | **T-114** BIM site / earthwork (toposolids) | A | Architect + civil persona depth; basic site only today. |
| 43 | **T-113** BIM structural grid + framing (Revit Structure / Robot / Tekla) | A | Architect-structural-engineer depth; early today. |
| 44 | **T-115** BIM material catalogue with render appearance | A | Architect-persona presentation depth; PBR shipped, BIM-bound material library is the gap. |
| 45 | **T-108** Full joint system (rigid / revolute / slider / cam / gear / pin-slot) | A | Mechanical persona depth; `kerf-mates` ships a constraint solver but fewer joint types than Inventor / SolidWorks / Onshape. |
| 46 | **T-102** Interactive push-and-shove diff-pair tuning | A | ECAD-persona depth; Kerf has length tuning, KiCad has interactive push-and-shove. |
| 47 | **T-103** Broader ECAD import (Allegro / PADS / gEDA / Eagle v10) | A | ECAD-persona reach; KiCad-oriented import path is the only one today. |
| 48 | **T-107** Direct + parametric history coexistence | B | Cross-sector authoring depth (Fusion / Inventor / Onshape class); Kerf is feature-tree primary. |
| 49 | **T-105** SubD authoring with creases + edit workflow | B | Cross-sector (jewelry / industrial-design / character / marine hull) authoring depth; `subd.py` + quad-remesh shipped, no creation/edit workflow. |
| 50 | **T-106** Render caustics + dispersion solver | B | Cross-sector presentation depth (jewelry / automotive / architecture). PBR + HDRI + bloom shipped this session; no Cycles / V-Ray / Enscape / KeyShot-class caustic transport. |

> Sub-tasks within a sequenced group (e.g. 5a–5e, 10a–10d, 12a–12f) keep
> their `Depends-on` chain; the loop completes a group's prerequisites in
> order before the next ranked group.

---

**How to add a task:** copy the template, give it the next free `T-<n>`,
fill **every** field (including **Tier** + **Money/reach rationale**), then
splice it into the ranked execution-order table above by the
people × sectors × revenue ÷ effort logic. Split anything bigger than ~one
agent-run into sequenced sub-tasks with `Depends-on`. A new uncovered sector
→ a P3 task + a P3 line in the roadmap. Keep this file and the roadmap in
sync when priorities change.

**Policy:** Advanced cross-cutting capabilities (ROADMAP §3.5) and long-term
horizon sectors (§6) are intentionally NOT enumerated as tasks here until
promoted to near-term P0/P1.

Template:

```
### T-<n> <title>
- **Tier:** A | B
- **Money/reach rationale:** <which & how-many personas/sectors unlocked + revenue logic>
- **Priority:** P<0-3>
- **Status:** 🔴 not started
- **Scope:** <what + why, 2-4 sentences>
- **Target files/packages:** <paths>
- **Definition of Done:** <concrete: tests / criteria>
- **Depends-on:** <T-ids or none>
```

---

<!-- Status reconciled 2026-05-16: T-1/T-2/T-3/T-5/T-6/T-7/T-8/T-9/T-10/T-11/T-12/T-13/T-14/T-20–T-27/T-28/T-29/T-30/T-31/T-32/T-33/T-34/T-35/T-37/T-40–T-46/T-90/T-91 flipped 🔴→✅. Left 🔴: T-4 (bend table), T-15/T-16 (large-assembly harness/LOD), T-36 (3D harness), T-47/T-48/T-50/T-51/T-52/T-53/T-70/T-71. -->
<!-- Status reconciled 2026-05-17 (geometry kernel — depth): the GK-NN
     backlog in docs/plans/geometry-kernel-roadmap.md (separate from this
     T-NN file) had its P0 (robustness foundation) + P1 (5 streams) + P3
     keystone (parametric history DAG + persistent face/edge naming) all
     land in packages/kerf-cad-core/src/kerf_cad_core/geom/. 620 hermetic
     kernel tests green (counts verified via `pytest --collect-only` per
     file in the plan). P2 (pure-Python STEP/IGES + SubD↔NURBS + mesh→NURBS
     autosurface + 2D region boolean) is the next ranked GK-NN focus and
     surfaces above T-50/T-51/T-52/T-53/T-70/T-71 in opus-spine priority. -->
<!-- Status reconciled 2026-05-17 (sector-depth gaps): added T-100..T-115
     for the depth gaps now tracked in ROADMAP §4.5 — FEM matching
     CalculiX/Z88/Mystran (T-100, in flight), CFD CfdOF-class (T-101, in
     flight), interactive diff-pair routing (T-102), broader ECAD import
     (T-103), kernel G3 / Phase-4 trim-by-curve / class-A leading (T-104,
     in flight), SubD authoring (T-105), render caustics + dispersion
     (T-106), direct + parametric history coexistence (T-107), full joint
     system (T-108), BIM family system (T-109), BIM family library
     (T-110), BIM walls/doors/windows/slabs full (T-111), BIM stairs/ramps
     full (T-112), BIM structural grid + framing (T-113), BIM site /
     earthwork toposolids (T-114), BIM material catalogue (T-115). T-100
     / T-101 / T-104 carry 🚧 in flight; the rest 🔴. -->

> **Geometry kernel — depth (2026-05-17).** Major step-change landed
> outside the T-NN backlog, on the GK-NN backlog in
> [`docs/plans/geometry-kernel-roadmap.md`](./docs/plans/geometry-kernel-roadmap.md):
> validated B-rep topology, tolerant pure-Python solid booleans, G1/G2
> fillets that trim + sew, edge chamfer, surface/curve/loop offsets,
> Coons patches, hardened SSI (rational-weight bug fix), closest-point,
> and a parametric history DAG with persistent face/edge naming. The
> opus spine continues there next, **on P2 (interop fidelity: pure-Python
> STEP/IGES + SubD↔NURBS + mesh→NURBS autosurface + 2D region boolean)**.
> Pull from that file's §4 between T-NN runs when an opus slot is free —
> kernel-depth wins compound under every persona at once.

## Tier A — persona unlocks (revenue)

### T-9 Gerber/fab: RS-274X writer
- **Tier:** A
- **Money/reach rationale:** Unlocks the **electronic engineer** persona
  (1 large paying professional workforce; 1 sector — ECAD). Design side is
  already KiCad-class, so this is the first artifact toward flipping a P0
  persona from 🔴 *cannot manufacture* → can. Hard willingness-to-pay: no
  fab output means no shippable product.
- **Priority:** P0
- **Status:** ✅ shipped
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
- **Tier:** A
- **Money/reach rationale:** Second mandatory fab artifact for the same
  ECAD persona. Cheap (same package as T-9), hard gate — a board with no
  drill file cannot be manufactured.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** CircuitJSON pad/via holes → Excellon drill file (tool table,
  plated/non-plated, drill hits). Pairs with T-9 in the fab package.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/excellon.py`.
- **Definition of Done:** tool table matches distinct hole sizes; hit count
  equals pad/via count; pytest with a fixture board.
- **Depends-on:** T-9

### T-11 Gerber/fab: pick-and-place + fab BOM
- **Tier:** A
- **Money/reach rationale:** Third fab artifact (assembly houses require
  P&P + fab BOM) for the ECAD persona. Reuses the shipped BOM rollup → low
  effort, same high-value persona.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Centroid/rotation pick-and-place CSV (top/bottom) + fab BOM
  CSV (refdes, value, footprint, distributor). Reuse the existing BOM rollup.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/pnp.py`, `fab_bom.py`.
- **Definition of Done:** P&P rows = placed components with correct
  side/rotation; fab BOM groups by value+footprint; pytest.
- **Depends-on:** T-9

### T-12 Gerber/fab: IPC-2581 / ODB++ + fab zip bundle
- **Tier:** A
- **Money/reach rationale:** The *actual* deliverable a fab house ingests —
  the moment the **electronic engineer** persona crosses 🔴→✅. Completes
  the single biggest P0 credibility blocker; a large paying persona is fully
  unlocked.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Single `export_fab_package` tool that bundles T-9/T-10/T-11
  outputs + an IPC-2581 XML (ODB++ optional) into one downloadable zip — the
  actual deliverable a fab house ingests.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  fab/ipc2581.py`, `tools/fab.py`, `PCBView.jsx` "Export fab package" button.
- **Definition of Done:** zip contains Gerbers + drill + P&P + BOM +
  IPC-2581; IPC-2581 validates against the schema in a test.
- **Depends-on:** T-9, T-10, T-11

### T-20 Jewelry worker op: `opGemstone`
- **Tier:** A
- **Money/reach rationale:** Flips the **jewelry CAD** persona from
  shipped-but-dead → usable (1 high-margin niche persona). Build cost is
  already paid (Python toolkit + UI + `.gem` migration shipped); only the JS
  worker wiring remains → extraordinary revenue-per-effort. Sub-task 5a.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Wire the `opGemstone` handler in the OCCT worker so the
  shipped `kerf_cad_core.jewelry.gemstones` node specs render the 7 cuts.
  This is the existing tracked jewelry-render work — split per op so each
  fits one agent run.
- **Target files/packages:** `src/lib/occtWorker.js` (`opGemstone`, wired
  into both `evaluateTree` ≈L3136 and `evaluateToFinalShape` ≈L3546),
  vitest in `src/__tests__/`.
- **Definition of Done:** gemstone node from `.gem`/`.feature` produces a
  tessellated mesh; round/brilliant facet count assertion; vitest dispatch.
- **Depends-on:** none

### T-21 Jewelry worker op: `opGemSeat`
- **Tier:** A
- **Money/reach rationale:** Same jewelry persona unlock (sub-task 5b);
  build cost already paid, only wiring remains.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Wire `opGemSeat` (seat/bearing cutter from
  `kerf_cad_core.jewelry.gem_seat`).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** seat node renders; cut-against-shank produces a
  valid solid; vitest.
- **Depends-on:** T-20

### T-22 Jewelry worker ops: prong head + bezel
- **Tier:** A
- **Money/reach rationale:** Same jewelry persona unlock (sub-task 5c);
  wiring-only against a shipped Python toolkit.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Wire `opJewelryProngHead` and `opJewelryBezel` (from
  `kerf_cad_core.jewelry.settings`).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** both ops render; prong count matches the spec;
  vitest dispatch for each.
- **Depends-on:** T-21

### T-23 Jewelry worker ops: channel + pavé
- **Tier:** A
- **Money/reach rationale:** Same jewelry persona unlock (sub-task 5d);
  wiring-only.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Wire `opJewelryChannel` and `opJewelryPave` (auto-array on a
  surface).
- **Target files/packages:** `src/lib/occtWorker.js`, vitest.
- **Definition of Done:** pavé array places N stones on a target surface;
  channel rail renders; vitest.
- **Depends-on:** T-22

### T-24 Jewelry worker op: `opRingShank` + end-to-end ring
- **Tier:** A
- **Money/reach rationale:** Completes the jewelry persona unlock
  (sub-task 5e) — a full assembled ring with metal-cost is the persona's
  end deliverable. Highest single revenue-per-effort step of the group:
  flips a fully-built-but-dead niche to revenue-generating.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Wire `opRingShank` (from `kerf_cad_core.jewelry.ring`, 7 shank
  profiles + sizer) and add an end-to-end test: shank + seat + prongs +
  stone renders as one assembled ring, with metal-cost panel populated.
- **Target files/packages:** `src/lib/occtWorker.js`,
  `src/__tests__/jewelryRingIntegration.test.js` (WASM-gated).
- **Definition of Done:** full ring renders; metal-weight/cost computed;
  WASM-gated integration test.
- **Depends-on:** T-23

### T-5 DWG/DXF: DXF reader (entities → Kerf primitives)
- **Tier:** A
- **Money/reach rationale:** First step of the **one feature that unlocks
  THREE big personas** — drafter + architect + automotive (3 sectors, large
  combined workforce). DWG/DXF is the linchpin for all three; only a narrow
  `.draft`→DXF-R12 *writer* exists, so this is general drawing/model
  exchange, not from-zero. Top reach-weighted revenue.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Pure-Python DXF (R12/2000+) reader: LINE/LWPOLYLINE/CIRCLE/ARC/
  TEXT/INSERT → an intermediate entity model. Read is currently absent
  entirely (only a narrow `.draft`→DXF-R12 *writer* exists).
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/`
  (new `dxf/` package: `reader.py`, `entities.py`).
- **Definition of Done:** parses committed fixture DXFs into the entity
  model; pytest covering each supported entity + an INSERT/BLOCK.
- **Depends-on:** none

### T-6 DWG/DXF: entity map → `.sketch` / `.drawing`
- **Tier:** A
- **Money/reach rationale:** Makes the inbound DXF path usable — drafter +
  architect can *open* industry files. Completes the inbound half of the
  3-persona unlock.
- **Priority:** P0
- **Status:** ✅ shipped
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
- **Tier:** A
- **Money/reach rationale:** The supplier-exchange / homologation
  deliverable for drafter + mechanical + automotive — outbound half of the
  3-persona unlock. Generalizes the existing R12 writer (lower effort than
  from-zero).
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** `kerf_imports.dxf_writer` — pure-Python general DXF writer
  supporting R12 + R2004 (AC1018); entities: LINE, LWPOLYLINE/POLYLINE,
  CIRCLE, ARC, ELLIPSE, SPLINE, TEXT, MTEXT, DIMENSION, HATCH, INSERT/BLOCK,
  LEADER; TABLES: LAYER/LTYPE/STYLE/DIMSTYLE; `dxf_export()` / `dwg_note()`;
  `export_dxf` LLM tool registered. DWG via ODA external (documented in
  `dwg_note()` and `kerf_imports.dwg.bridge`).
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/dxf_writer.py`,
  `packages/kerf-imports/tests/test_dxf_writer.py`.
- **Definition of Done:** 58 hermetic pytest tests; all pass; reader(writer(x))
  == x for mixed-entity samples.
- **Depends-on:** T-5

### T-90 Privacy: paid-tier projects default to private (cloud)
- **Tier:** A
- **Money/reach rationale:** Privacy is a classic paid conversion lever —
  it raises willingness-to-pay across **every cloud persona** (private
  projects is the single most common reason hobbyists upgrade to a paid
  tier). Tiny isolated change keyed off the existing billing buckets → very
  high revenue-per-effort. **Self-hosted: N/A** (no Workshop, no public
  concept) — explicitly do no work on the self-hosted path.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** In **cloud mode**, a paid-tier user's newly created projects
  default to `visibility='private'`; free-tier cloud users keep the current
  public-spirited default (Workshop free-sharing ethos). The `projects`
  table already has `visibility` (`private`/`unlisted`/`public`, default
  `private` — migration 001); the change is the **create-project default**
  being chosen by billing tier rather than a hard constant, plus the UI
  default in the create dialog. Workshop publish must remain an **explicit
  opt-in** regardless of tier (today `POST /api/workshop/publish` sets
  `visibility='public'` owner-only, idempotent — leave that gated and
  explicit; do not auto-publish anything).
- **Target files/packages:** `packages/kerf-api/src/kerf_api/routes.py`
  (`create_project` ≈L857: choose default visibility from the user's
  billing tier), bucket/tier lookup via
  `packages/kerf-billing/src/kerf_billing/buckets.py` /
  `packages/kerf-cloud/src/kerf_cloud/` (paid vs free), create-project UI
  default in `src/` (project-create dialog). No self-hosted code path.
- **Definition of Done:** in cloud mode a simulated paid-tier user's
  created project is `private` by default and a free-tier user's is the
  prior default; Workshop publish still requires the explicit endpoint and
  is unaffected; self-hosted/local path unchanged (asserted in a test);
  pytest for the tier→default mapping.
- **Depends-on:** none

### T-91 Privacy default: test coverage + UI copy
- **Tier:** A
- **Money/reach rationale:** Guards the revenue lever from regression and
  makes the value legible to the user (the "your projects are private"
  signal is itself a conversion message). Same every-cloud-persona reach as
  T-90.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Add the end-to-end + UI test coverage and the user-facing copy
  for T-90: paid → private default, free → existing default, self-hosted
  unaffected, Workshop publish still explicit. Surface a small "private by
  default (paid)" hint in the create-project dialog.
- **Target files/packages:** `packages/kerf-api/tests/` (visibility-default
  cases), `src/__tests__/` or Playwright (create-dialog default + copy),
  create-project dialog component in `src/`.
- **Definition of Done:** tests cover all four matrix cells (paid/free ×
  cloud/self-hosted) + the explicit-publish invariant; the create dialog
  shows the tier-appropriate default and copy; green in CI.
- **Depends-on:** T-90

### T-1 Sheet metal: flange op + `.feature` schema
- **Tier:** A
- **Money/reach rationale:** Sheet metal is the **biggest single mechanical
  sub-need** and BIW stamping for **automotive** — two large paying
  personas, one P0 capability. First sub-task (10a) of the 4-step group;
  bigger total effort than the cheaper persona-unlocks, hence ranked just
  below them.
- **Priority:** P0
- **Status:** ✅ shipped
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
- **Tier:** A
- **Money/reach rationale:** Same mechanical + automotive unlock
  (sub-task 10b); the neutral-axis unfold math is the core of the
  flat-pattern deliverable both personas need.
- **Priority:** P0
- **Status:** ✅ shipped
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
- **Tier:** A
- **Money/reach rationale:** Same mechanical + automotive unlock
  (sub-task 10c); the flat pattern is the literal manufacturing handoff for
  sheet-metal parts.
- **Priority:** P0
- **Status:** ✅ shipped
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
- **Tier:** A
- **Money/reach rationale:** Completes the mechanical sheet-metal unlock
  (sub-task 10d) — production shops require per-material/thickness bend
  tables, not a single k-factor.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Add a per-material/thickness bend-table (`.bendtable` data or
  rows in the material DB) so flange/unfold pick allowance from a table
  rather than a single k-factor. End-to-end integration test.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  sheet_metal.py`, materials DB seed, integration test.
- **Definition of Done:** table lookup overrides scalar k-factor when
  present; integration test fold→unfold→flat with a real bend table.
- **Depends-on:** T-3

### T-8 DWG/DXF: DWG read via ODA/libredwg bridge (eval)
- **Tier:** A
- **Money/reach rationale:** Extends the 3-persona DXF unlock to true
  **DWG** — architecture and automotive run on DWG, not just DXF, so this
  closes the last gap of the biggest reach-weighted revenue feature.
  Bridge-eval effort, hence after the cheaper wins.
- **Priority:** P0
- **Status:** ✅ shipped
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

### T-13 Persistent face naming: boolean-heavy regression corpus
- **Tier:** A
- **Money/reach rationale:** Protects *every* persona's revenue — a
  topo-naming failure under booleans breaks the chat-driven core for all
  sectors at once. Not a new unlock (hence not top-ranked), but a
  cross-sector correctness moat.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Build a regression corpus of boolean-heavy `.feature` models
  (cut/fuse/common chains, pattern-then-fillet, sketch-edit-then-reeval) and
  assert face-name stability across re-eval. Hardens the shipped T1–T2.
- **Target files/packages:** `src/__tests__/faceNamingRegression.test.js`,
  fixture `.feature` JSON under `src/__tests__/fixtures/`.
- **Definition of Done:** ≥10 boolean-heavy fixtures; each asserts that a
  named face survives an upstream sketch edit; failures pinpoint the op.
- **Depends-on:** none

### T-14 Persistent face naming: boundary-face naming on booleans
- **Tier:** A
- **Money/reach rationale:** Same all-persona correctness moat; closes the
  open question in the persistent-face-naming plan so booleans are safe for
  every sector.
- **Priority:** P0
- **Status:** ✅ shipped
- **Scope:** Implement deterministic naming for faces *created by* boolean
  ops (the open question in `docs/plans/persistent-face-naming.md`) using
  the OCCT Modified/Generated maps already extracted in T2.
- **Target files/packages:** `src/lib/faceNaming.js`, `src/lib/occtWorker.js`.
- **Definition of Done:** T-13 corpus passes for boolean-boundary faces;
  unit tests for `nameOpOutput` on cut/fuse/common with shared edges.
- **Depends-on:** T-13

### T-15 Large-assembly perf harness + measured ceiling
- **Tier:** A
- **Money/reach rationale:** Unblocks mechanical + architect + automotive
  at scale (3 personas) — full-vehicle DMU (10,000s of parts) is the
  extreme case. Harness-first defines the budget before any loader work.
- **Priority:** P0
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
- **Tier:** A
- **Money/reach rationale:** Same 3-persona scale unlock; raises the
  measured ceiling so large assemblies stop disqualifying Kerf in minute
  one for mechanical/architect/automotive.
- **Priority:** P0
- **Status:** 🔴 not started
- **Scope:** Bounding-box/proxy LOD + lazy mesh fetch for assembly
  components beyond a count threshold, driven by the T-15 budget.
- **Target files/packages:** assembly render path in `src/`, `assembly.js`.
- **Definition of Done:** T-15 harness shows the ceiling raised by the
  target factor at 10k parts; vitest for the LOD-selection logic.
- **Depends-on:** T-15

### T-31 ECAD: 3D board STEP export
- **Tier:** A
- **Money/reach rationale:** Deepens the freshly-unlocked **electronic
  engineer** persona into MCAD-ECAD co-design (the cross-project
  PCB-as-part path consumes it) — extends revenue from a persona already
  converting after the fab-output unlock.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** CircuitJSON board + component 3D models → a STEP assembly for
  MCAD-ECAD co-design (the cross-project PCB-as-part path consumes it).
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/
  ` (new `board_step.py`), tool + doc.
- **Definition of Done:** board outline + placed component STEPs export as
  one STEP that reloads; pytest (OCC-gated).
- **Depends-on:** none

### T-37 Surface-boolean robustness on dense NURBS
- **Tier:** A
- **Money/reach rationale:** Reliability moat for **jewelry + automotive**
  (2 personas) — protects the jewelry revenue just unlocked (T-20…T-24) and
  the Class-A automotive path; organic models must survive booleans.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Eliminate runtime escalation paths in `opSurfaceBoolean` so
  dense organic NURBS survive booleans reliably (fuzzy-value tuning,
  ShapeFix pre-pass strategy, deterministic fallback ordering).
- **Target files/packages:** `src/lib/occtWorker.js` (`opSurfaceBoolean`),
  `src/lib/occtBridge.js`, WASM-gated integration tests.
- **Definition of Done:** a dense-NURBS boolean corpus passes without the
  C1-T10 escalation; WASM-gated integration test green in CI.
- **Depends-on:** none

### T-35 Class-A: zebra / reflection-line analysis (the shippable slice)
- **Tier:** A
- **Money/reach rationale:** The cheap, no-WASM Class-A credibility win for
  the **automotive** persona — a visible surface-quality signal that
  converts automotive evaluators. Low effort (shader-side only).
- **Priority:** P1
- **Status:** ✅ shipped
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

### T-25 Weldments: structural member op
- **Tier:** A
- **Money/reach rationale:** Converts the **mechanical** persona deeper
  (structural fabrication is a common mechanical deliverable). Sub-task 22a.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** `weldment_member` feature: a profile (from a standard-section
  table) swept along selected sketch path segments, with trim-at-joint.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  weldment.py`, `src/lib/occtWorker.js` (`opWeldmentMember`), FeatureView,
  doc page.
- **Definition of Done:** members along a 3-segment path with mitred
  joints; pytest schema + vitest dispatch.
- **Depends-on:** none

### T-26 Weldments: cut list
- **Tier:** A
- **Money/reach rationale:** Completes the mechanical weldments deliverable
  (sub-task 22b) — a cut list is the fabrication handoff.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Roll up weldment members into a cut list (profile, length,
  qty, angle) reusing the BOM rollup pattern.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  weldment.py`, a cut-list view.
- **Definition of Done:** cut list groups identical members; CSV export;
  pytest.
- **Depends-on:** T-25

### T-27 GD&T-from-model: model-driven datum + tolerance callouts
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive correctness/standards
  depth (2 personas) — frames already render; the model→callout link is the
  gap. Standards features are *more* important under an LLM, not less.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Attach datums + geometric tolerances to model faces/edges and
  have the drawing engine place the GD&T frame automatically on projected
  views (frames already render; the model→callout link is the gap).
- **Target files/packages:** `.feature` schema (datum/tolerance slots),
  drawing projection code, LLM tool + doc.
- **Definition of Done:** a toleranced model face produces a positioned
  GD&T frame on its drawing view; pytest + vitest.
- **Depends-on:** none

### T-28 IFC import Tier 2: openings + MEP
- **Tier:** A
- **Money/reach rationale:** Deepens the **architect** persona — interop
  with the real BIM ecosystem (openings + MEP) is a hard requirement for
  professional adoption. Sub-task 24a.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Extend `kerf_bim.import_ifc` (Tier 1 today) to parse
  `IfcOpeningElement` (windows/doors) and `IfcDistributionElement` (MEP)
  into `.bim` JSON.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/import_ifc/`
  (new `openings.py`, `mep.py`), parser wiring.
- **Definition of Done:** fixture IFC with openings + MEP imports
  correctly; hermetic-mock pytest like the Tier-1 suite.
- **Depends-on:** none

### T-29 IFC import Tier 2: families + schedules + views
- **Tier:** A
- **Money/reach rationale:** Same architect-persona depth (sub-task 24b) —
  families/schedules/views complete BIM round-trip.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Parse IFC type objects → `.family.json`, quantity sets →
  `.schedule.json`, plan/section context → `.view.json`.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/import_ifc/`
  (`families.py`, `schedules.py`).
- **Definition of Done:** fixture IFC produces valid family/schedule JSON;
  pytest.
- **Depends-on:** T-28

### T-30 Parametric family editor (Revit moat)
- **Tier:** A
- **Money/reach rationale:** Architect-persona depth + a recognized
  competitive moat (Revit's signature capability) — a strong conversion
  argument for the architect segment.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** A `.family.json`-authoring flow where parameters drive nested
  geometry (extends the shipped `.family` data model into a true parametric
  editor with constraints + flex test).
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/tools/
  family.py`, `src/lib/family.js`, editor.
- **Definition of Done:** a parametric column family flexes correctly
  across parameter sets; pytest + vitest "flex" test.
- **Depends-on:** none

### T-36 3D wiring harness: route-through-DMU primitive
- **Tier:** A
- **Money/reach rationale:** Automotive + ECAD depth (2 personas) — today
  only 2D WireViz exists; a 3D harness opens a new deliverable for two
  personas already on the path.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** A `harness_segment` op that routes a bundle along a 3D path
  with diameter from a wire list — the primitive 3D harness needs (today
  only 2D WireViz exists). Formboard flatten + voltage-drop are later tasks.
- **Target files/packages:** `packages/kerf-wiring/src/kerf_wiring/` (new
  3D module), `src/lib/occtWorker.js` (sweep-based bundle), doc.
- **Definition of Done:** a bundle routes along a 3-point path with correct
  diameter; length computed; pytest + vitest.
- **Depends-on:** none

### T-50 FEM: nonlinear material (plasticity) path
- **Tier:** A
- **Money/reach rationale:** First step of the broad simulation pillar
  (mechanical + automotive). P2 — moat depth rather than a P0 persona
  unlock, hence ranked below the P0/P1 conversion tasks.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Add a nonlinear (J2 plasticity) `analysis_type` to the FEM
  solver (today the verified enum is `linear_static | modal | thermal`
  only). First step of the broader nonlinear/crash/fatigue line.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/` (solver +
  `tools.py` enum), tests (analytical cantilever-yield reference).
- **Definition of Done:** nonlinear run matches an analytical
  elastic-plastic reference within tolerance; engine-absent → sentinel.
- **Depends-on:** none

---

## Tier B — cross-sector multipliers (reach / funnel)

### T-40 Workshop README: schema (`readme` markdown field + migration)
- **Tier:** B
- **Money/reach rationale:** First step of repositioning Workshop from a
  Thingiverse-style image gallery into **GitHub-for-parametric-CAD** —
  benefits *every* sector simultaneously (more discoverable, forkable,
  documented assets ⇒ more SEO, more evaluators, more fork→convert). The
  largest single top-of-funnel multiplier. Sub-task 12a.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Add a `readme` markdown field to the workshop publish/project
  record via a new numbered migration (current highest is
  `060_kind_gem.sql`, so `061_workshop_readme.sql`), following the
  numbered-migration convention in
  `packages/kerf-core/src/kerf_core/db/migrations/`. Schema only; no
  generation or rendering yet.
- **Target files/packages:**
  `packages/kerf-core/src/kerf_core/db/migrations/061_workshop_readme.sql`
  (new), any read/write of the project/workshop record in
  `packages/kerf-api/src/kerf_api/routes.py` that must round-trip the field.
- **Definition of Done:** migration applies cleanly forward; the publish
  record persists and returns a `readme` string; pytest asserting
  round-trip; existing workshop tests still green.
- **Depends-on:** none

### T-41 Workshop README: AI auto-generate on publish + regenerate action
- **Tier:** B
- **Money/reach rationale:** Makes every published project self-documenting
  with zero author effort — the core of the GitHub-for-CAD repositioning;
  cross-sector funnel + fork conversion. Sub-task 12b.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** On Workshop publish, AI-generate the README (default on)
  composed from project params + BOM + the `kerf_parts` provenance/part
  attribution block + a fork/edit guide + license, via the existing LLM
  tool path; store it in the T-40 field. Add an explicit "regenerate"
  action. (Decisions are LOCKED: AI-generated-on-publish is the default.)
- **Target files/packages:** workshop-publish handler in
  `packages/kerf-api/src/kerf_api/routes.py` (the `POST /api/workshop/
  publish` path ≈L4880), the LLM tool path
  (`packages/kerf-chat/`), README composition helper.
- **Definition of Done:** publishing a fixture project produces a stored
  README containing params + BOM + part attribution + fork guide + license
  sections; "regenerate" replaces it; mocked-LLM pytest (no live model
  call).
- **Depends-on:** T-40

### T-42 Workshop README: auto-rendered hero cover; gallery becomes optional
- **Tier:** B
- **Money/reach rationale:** A consistent auto-rendered hero per project
  makes the browse grid look like a curated catalog with zero author
  effort — raises perceived quality and click-through across all sectors.
  Sub-task 12c.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** On publish, auto-render a hero cover image via `kerf-render`
  and store it as the project's cover; the `project_workshop_images`
  gallery (migrations 052/055) becomes **optional**, not required.
  (Decisions LOCKED: auto-rendered cover + optional gallery.)
- **Target files/packages:** workshop-publish handler in
  `packages/kerf-api/src/kerf_api/routes.py`, `packages/kerf-render/src/
  kerf_render/` (render invocation), cover storage key on the project/
  workshop record.
- **Definition of Done:** publish produces a stored auto-cover; publish
  succeeds with zero gallery images; render-unavailable degrades gracefully
  to the existing auto-captured thumbnail fallback; pytest (mocked render).
- **Depends-on:** T-40

### T-43 Workshop README: public page (README-primary, XSS-safe render)
- **Tier:** B
- **Money/reach rationale:** The public-facing surface where the funnel
  actually converts — README-primary layout + auto-cover browse grid is
  the GitHub-for-CAD experience an evaluator from any sector lands on.
  Sub-task 12d.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Rebuild the public Workshop page so README is primary
  (sanitized / XSS-safe markdown render), the auto-rendered cover drives
  the browse grid, and the gallery is an *optional* secondary section.
  (Decisions LOCKED: README primary + auto-cover grid + optional gallery.)
- **Target files/packages:** `src/cloud/Workshop.jsx`,
  `src/cloud/WorkshopListing.jsx` (browse grid uses auto-cover; README
  primary; optional secondary gallery; sanitized markdown renderer).
- **Definition of Done:** a published project renders README primary with
  cover; a hostile markdown/HTML fixture is sanitized (no script
  execution); browse grid shows auto-cover; gallery section hidden when
  empty; vitest for the sanitizer + layout.
- **Depends-on:** T-41, T-42

### T-44 Workshop README: PublishButton/flow UX (preview/edit + regenerate)
- **Tier:** B
- **Money/reach rationale:** Lowers publish friction (gallery no longer
  mandatory) and gives authors confidence in the AI README — directly
  increases publish rate across every sector. Sub-task 12e.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Update the publish flow: README preview/edit + a "regenerate
  with AI" action; gallery upload is no longer mandatory. (Decisions
  LOCKED: gallery optional, AI-README default.)
- **Target files/packages:** `src/cloud/PublishButton.jsx` (README
  preview/edit, regenerate action, gallery optional).
- **Definition of Done:** publish completes with no gallery images; README
  preview shows the AI draft, is editable, and "regenerate" re-fetches;
  vitest for the flow states.
- **Depends-on:** T-41

### T-45 Workshop README: tests (schema, XSS, render fallback, mocked LLM)
- **Tier:** B
- **Money/reach rationale:** Locks the funnel-multiplier in against
  regression (a broken Workshop page silently kills the top of funnel for
  every sector). Sub-task 12f.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Consolidated test pass for the Workshop README workstream:
  schema round-trip, markdown XSS sanitization, render-fallback when
  `kerf-render` is unavailable, and mocked-LLM auto-generation.
- **Target files/packages:** `packages/kerf-api/tests/` (schema + auto-gen
  with mocked LLM + render fallback), `src/__tests__/` (XSS sanitizer +
  README-primary layout).
- **Definition of Done:** all four test areas green in CI; XSS fixture
  proves no script execution; render-absent path proves graceful fallback;
  LLM is mocked (no live call).
- **Depends-on:** T-40, T-41, T-42, T-43

### T-46 Parts-library: seed KiCad libraries via `kerf-parts`
- **Tier:** B
- **Money/reach rationale:** Turns the just-built parts pipeline into a
  *populated* electronics library — a cold-start killer for the **ECAD**
  persona (huge) right after the fab-output unlock makes ECAD shippable. An
  empty library is a silent conversion killer; this fixes it at scale.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Run/seed KiCad symbol+footprint libraries through the
  MIT-clean `kerf-parts` fetch/convert pipeline (the `kicad.py` adapter is
  the most complete) so the electronics parts library ships populated.
- **Target files/packages:** `packages/kerf-parts/src/kerf_parts/adapters/
  kicad.py`, seed/run path, tests (pinned fixture, no committed
  third-party data).
- **Definition of Done:** a pinned KiCad-lib fixture converts to ≥1 valid
  `kind='part'` file with provenance; the seed path is reproducible and
  documented; pytest with no committed third-party data.
- **Depends-on:** none

### T-34 kerf-partsgen: author standard fastener families
- **Tier:** B
- **Money/reach rationale:** Populates the **mechanical** side of the
  library via author-once-then-enumerate — a cold-start killer across *all*
  mechanical sectors; zero-token enumeration ⇒ very cheap, very broad
  reach.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Add parametric generators for the next standard families
  (ISO 4762 socket-head cap screw, ISO 4032 hex nut, DIN 125 washer) using
  the author-once-then-enumerate framework. One family per agent run.
- **Target files/packages:** `packages/kerf-partsgen/src/kerf_partsgen/
  generators/`, `verify.py` fixtures.
- **Definition of Done:** each generator enumerates its full SIZES table
  deterministically (zero tokens) and passes `verify.py` geometry checks.
- **Depends-on:** none

### T-47 Parts-library: jewelry generated-parts render check
- **Tier:** B
- **Money/reach rationale:** Closes the parts-library loop for the
  now-usable **jewelry** persona — ensures jewelry generated parts actually
  render in the library, so the high-margin niche has a populated catalog
  too.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Verify (and fix as needed) that jewelry parts generated via
  the toolkit render correctly as library parts now that the jewelry worker
  ops are wired (T-20…T-24) — a render-path / library-integration check,
  not new geometry.
- **Target files/packages:** `packages/kerf-parts/` and/or
  `packages/kerf-cad-core/src/kerf_cad_core/jewelry/`, library render path,
  integration test.
- **Definition of Done:** a generated jewelry part appears in the library
  and renders via the wired worker ops; integration test (WASM-gated where
  applicable).
- **Depends-on:** T-24

### T-48 Education / maker on-ramp: simple-parametric + cut-list / flat-pack path
- **Tier:** B
- **Money/reach rationale:** Biggest *raw reach* + the mission persona
  (ROADMAP §2 — largest workforce, democratizing design). Slicing + CAM are
  already shipped, so a polished simple-parametric + cut-list/flat-pack
  path + clear on-ramp grows the widest possible top-of-funnel for the
  smallest incremental effort.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Polish the simple-parametric + cut-list / flat-pack path and
  add a clear on-ramp for the education/maker/hobbyist persona: a guided
  "design a part / enclosure / furniture piece + get a cut list" flow that
  leans on the shipped slicing (`packages/kerf-slicing`) and CAM
  (`packages/kerf-cam`).
- **Target files/packages:** simple-parametric + cut-list path in `src/`
  and `packages/kerf-cad-core/`, an on-ramp entry surface, LLM doc page.
- **Definition of Done:** a maker can go from a parametric prompt to a
  printable/CNC-able part **and** a flat-pack cut list in the guided flow;
  the cut list exports; pytest/vitest covering the cut-list math + flow.
- **Depends-on:** none

### T-32 kerf-parts: complete bolts adapter
- **Tier:** B
- **Money/reach rationale:** Further populates the mechanical/ECAD parts
  ecosystem (scaffold-stage BOLTS adapter → working) — a reach multiplier
  that lowers cold-start across mechanical sectors.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Finish the scaffold-stage BOLTS adapter
  (`adapters/bolts.py`) so BOLTS fasteners convert into native library
  parts through the MIT-clean fetch/convert pipeline.
- **Target files/packages:** `packages/kerf-parts/src/kerf_parts/adapters/
  bolts.py`, tests.
- **Definition of Done:** a pinned BOLTS fixture converts to ≥1 valid
  `kind='part'` file with provenance; pytest (no committed third-party data).
- **Depends-on:** none

### T-33 kerf-parts: complete freecad-library adapter
- **Tier:** B
- **Money/reach rationale:** Same parts-ecosystem reach multiplier for the
  mechanical side (scaffold-stage FreeCAD-library adapter → working).
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Finish the scaffold-stage FreeCAD-library adapter
  (`adapters/freecad_library.py`).
- **Target files/packages:** `packages/kerf-parts/src/kerf_parts/adapters/
  freecad_library.py`, tests.
- **Definition of Done:** a pinned fixture converts to valid native parts;
  pytest.
- **Depends-on:** none

### T-51 Clash detection across disciplines
- **Tier:** B
- **Money/reach rationale:** Cross-sector platform multiplier (architect +
  mechanical) — a coordination capability that helps any multi-discipline
  project. P2.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Pairwise interference check across assembly components /
  IFC elements, producing a clash report.
- **Target files/packages:** new module + LLM tool + report view.
- **Definition of Done:** known-overlapping fixture yields the expected
  clash set; pytest.
- **Depends-on:** none

### T-52 Scan-to-CAD: point-cloud ingest + primitive fit
- **Tier:** B
- **Money/reach rationale:** High-leverage cross-cutting reverse-
  engineering seed — touches mechanical, architecture, automotive, and
  medical at once. P2.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Ingest a point cloud (PLY/E57 subset) and fit basic
  primitives (plane/cylinder/sphere) — the high-leverage reverse-engineering
  seed.
- **Target files/packages:** new import package + tool + viewer.
- **Definition of Done:** synthetic cloud → correct fitted primitives
  within tolerance; pytest.
- **Depends-on:** none

### T-53 Nesting / cut-optimization for sheet/laser
- **Tier:** B
- **Money/reach rationale:** Cross-sector fabrication multiplier (one
  solver serves laser/waterjet/plasma/wood/sheet); consumes the sheet-metal
  flat patterns. P2.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** 2D part nesting (bin-packing with rotation) for laser/waterjet
  cut sheets; consumes sheet-metal flat patterns.
- **Target files/packages:** new module + tool + layout view.
- **Definition of Done:** a part set nests within a sheet with measured
  utilization; pytest on the packing math.
- **Depends-on:** T-3

### T-70 Civil engine seed: geospatial CRS + TIN terrain
- **Tier:** B
- **Money/reach rationale:** Highest raw societal importance
  (water/sanitation/roads, esp. developing world) but engine-gated → P3.
  This is the proof-of-"we do everything" civil seed; reach is long-term,
  hence ranked at the tail.
- **Priority:** P3
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
- **Tier:** B
- **Money/reach rationale:** NURBS-reachable long-tail vertical — close to
  Kerf's existing NURBS strength, so a cheap P3 proof seed that broadens
  sector coverage.
- **Priority:** P3
- **Status:** 🔴 not started
- **Scope:** A hull-surface fairing helper that builds a lofted hull from
  station offsets and reports fairness via the existing curvature-comb
  infra — close to Kerf's NURBS strength, hence a good early P3 pick.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/`
  (hull helper reusing `surfacing.py`), doc.
- **Definition of Done:** offset table → faired hull surface; curvature
  combs render on it; pytest schema + vitest dispatch.
- **Depends-on:** none

---

## Sector depth gaps (G-1 … G-16, surfaced 2026-05-17)

Honest depth gaps against the reference tool in each sector. Mapped 1:1 to
ROADMAP [§4.5](./ROADMAP.md#§4-5--honest-depth-gaps-tracked-2026-05-17).
Tiering follows the same money/reach rule: BIM / FEM / CFD / ECAD depth →
Tier A (single persona unlock), render / SubD / direct-edit → Tier B
(cross-sector multiplier).

### T-100 FEM matching CalculiX / Z88 / Mystran depth
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive simulation depth
  (2 personas). Seed modules (`nonlinear`, `explicit`, `acoustics_fem`,
  `em_field`, `em_highfreq`, `fatigue_fem`) are already in
  `packages/kerf-fem/`; needs wiring through the public `analysis_type`
  enum + reference-tool match. FEM-hardening stream is in flight in
  parallel; this task captures **what's left after that lands**.
- **Priority:** P2
- **Status:** 🚧 in flight
- **Scope:** Wire the seed nonlinear / explicit / acoustics / EM /
  fatigue modules through the public analysis enum + LLM tool surface,
  then match a CalculiX (nonlinear / contact) + Z88 (linear / modal /
  nonlinear) + Mystran (modal / aeroelastic) reference test corpus.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/` (`tools.py`
  analysis-enum extension, plugin capability advertisements,
  `nonlinear.py` / `explicit.py` / `acoustics_fem.py` / `em_field.py` /
  `em_highfreq.py` / `fatigue_fem.py`), reference-test corpus under
  `packages/kerf-fem/tests/`.
- **Definition of Done:** each module passes its reference-tool match
  within tolerance; analysis-enum advertises the new types; capability
  tags appear in `GET /health/capabilities`.
- **Depends-on:** none

### T-101 CFD CfdOF-class — turbulence + 3-D meshing + OpenFOAM bridge
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive + aerospace
  simulation depth (3 personas, P2 — moat depth not P0 unlock). Potential
  flow (`cfd_potential.py`) is the seed already in flight; full CfdOF
  parity is engine-class.
- **Priority:** P2
- **Status:** 🚧 in flight
- **Scope:** Extend `cfd_potential.py` past the potential-flow seed into
  full Navier-Stokes + heat transfer with turbulence models (k-ε /
  k-ω SST), 3-D unstructured meshing, and an OpenFOAM bridge for the
  serious-CFD path (graceful degrade when the binary is absent, same
  pattern as CuraEngine / Instant-Meshes).
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_*.py`,
  optional `packages/kerf-fem/src/kerf_fem/openfoam_bridge.py`, tests.
- **Definition of Done:** known-solution NS run (lid-driven cavity)
  matches reference within tolerance; turbulence model toggle works;
  OpenFOAM bridge round-trips a fixture case with binary present →
  degrades to sentinel when absent.
- **Depends-on:** none

### T-102 ECAD: interactive push-and-shove diff-pair routing
- **Tier:** A
- **Money/reach rationale:** ECAD-persona depth — KiCad has interactive
  push-and-shove; Kerf has length tuning only. A visible UX-class quality
  signal that converts ECAD evaluators after the fab-output unlock.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** An interactive router that displaces neighbouring tracks
  out of the way as the user drags a new diff-pair, preserving net
  classes / clearance / length-match constraints. Builds on the shipped
  shove-router infrastructure.
- **Target files/packages:** `packages/kerf-electronics/src/
  kerf_electronics/routing/`, `src/components/PCBView.jsx` (interactive
  drag UX), tests.
- **Definition of Done:** dragging a diff-pair pushes neighbouring tracks
  while preserving the net class / clearance rules; vitest on the shove
  math + UX integration test.
- **Depends-on:** none

### T-103 ECAD: broader import (Allegro / PADS / gEDA / Eagle v10)
- **Tier:** A
- **Money/reach rationale:** ECAD-persona reach — today only the KiCad
  family imports; large parts of the working ECAD ecosystem live in
  Allegro / PADS / gEDA / Eagle. Each adapter unlocks a real workforce
  slice for the same persona.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Per-vendor adapter under `packages/kerf-imports/` that
  parses each vendor's design exchange format (or its open subset) into
  the same CircuitJSON / schematic / footprint shape KiCad imports
  produce today. Start with the cheapest (Eagle v10 XML); end on Allegro.
- **Target files/packages:** new `packages/kerf-imports/src/
  kerf_imports/{allegro,pads,geda,eagle}/`, tools + docs.
- **Definition of Done:** each adapter round-trips a pinned fixture
  to CircuitJSON; pytest with no committed third-party data.
- **Depends-on:** none

### T-104 Kernel G3 + NURBS Phase 4 trim-by-curve + class-A leading
- **Tier:** A
- **Money/reach rationale:** Automotive + jewelry Class-A surfacing
  depth (2 personas). G3 curvature combs partially shipped (#100);
  imprint (GK-19) + class-A leading still to go. Kernel-side depth →
  opus-spine; cross-sector reach via the surfacing path.
- **Priority:** P1
- **Status:** 🚧 in flight
- **Scope:** Extend the Phase-4 NURBS surfacing path past the shipped
  C0–C2 / G0–G2 + curvature combs into algorithmic G3 (custom-WASM
  required — stock OCCT cannot enforce `GeomAbs_G3`), full trim-by-curve
  / imprint (GK-19 in the geometry-kernel roadmap), and the class-A
  leading surface-quality workflow.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/` (G3 helpers, trim-by-curve, leading), tests; aligns with
  `docs/plans/geometry-kernel-roadmap.md` GK-NN slots.
- **Definition of Done:** G3 enforced across a blend / sweep + analytic
  oracle; trim-by-curve produces a valid trimmed face; leading workflow
  flags hot-spots on a class-A test surface; pytest.
- **Depends-on:** none

### T-105 SubD authoring with creases + edit workflow
- **Tier:** B
- **Money/reach rationale:** Cross-sector authoring depth (jewelry,
  industrial design, character, marine hull). `subd.py` + quad-remesh
  ship today, but **no SubD creation / edit / crease workflow** —
  Rhino 8's SubD is the reference.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Author-time SubD: create from primitives or convert from
  mesh; edge / vertex / face edit ops with crease weights; round-trip
  to the existing Catmull-Clark evaluator; UX surface.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/subd.py` (authoring API extensions), worker handler, tests, UX.
- **Definition of Done:** create-edit-evaluate round-trips on a SubD
  cube + cylinder; creases hold under subdivision; vitest dispatch +
  pytest math.
- **Depends-on:** none

### T-106 Render: caustics + dispersion solver
- **Tier:** B
- **Money/reach rationale:** Cross-sector presentation depth — jewelry
  (gem dispersion is the deliverable), automotive (paint / glass
  caustics), architecture (Enscape-class daylighting). PBR + HDRI +
  bloom shipped this session; the next-class jump is a real caustic
  transport solver.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** A caustic-transport renderer (photon-map or BDPT) wired
  into the existing `kerf-render` worker, plus a dispersion model for
  gem ray-trace. Cycles / V-Ray / Enscape / KeyShot are the reference.
- **Target files/packages:** `packages/kerf-render/src/kerf_render/`
  (caustic + dispersion modules), worker route, LLM tool, tests.
- **Definition of Done:** caustic spot from a glass sphere matches a
  Cycles reference render within delta-E tolerance; gem dispersion
  produces a chromatic fan; pytest gated on the renderer.
- **Depends-on:** none

### T-107 Direct + parametric history coexistence
- **Tier:** B
- **Money/reach rationale:** Cross-sector authoring depth (Fusion /
  Inventor / Onshape coexist direct + history). Kerf is feature-tree
  primary today; users editing imported "dumb" geometry need deeper
  direct editing alongside the parametric tree.
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Promote direct edits (face move / pull / patch / delete)
  into first-class feature nodes in the parametric DAG so a direct
  edit replays on parameter changes instead of being lost.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/history/` (direct-edit feature nodes), `src/lib/occtWorker.js`
  direct-edit handlers, UX.
- **Definition of Done:** a direct-face-move stays attached to its
  semantically-named face after an upstream sketch edit; pytest +
  vitest.
- **Depends-on:** none

### T-108 Full joint system (rigid / revolute / slider / cam / gear / pin-slot)
- **Tier:** A
- **Money/reach rationale:** Mechanical persona depth. `kerf-mates`
  ships a constraint solver but fewer joint types than Inventor /
  SolidWorks / Onshape. A real joint library is a conversion lever for
  the mechanical engineer persona deep in assembly authoring.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Add rigid / revolute / slider / cam / gear / pin-slot
  joint types to `kerf-mates` with motion ranges + drives + limits;
  wire each into the existing mate solver.
- **Target files/packages:** `packages/kerf-mates/src/kerf_mates/`
  (joints.py + solver wiring), LLM tools, tests.
- **Definition of Done:** each joint type has an analytic kinematics
  reference test; drives animate within limits; pytest.
- **Depends-on:** none

### T-109 BIM parametric family-authoring UX
- **Tier:** A
- **Money/reach rationale:** Architect-persona depth — Revit's signature
  capability. The Tier-2 family *import* path shipped (T-29); native
  family **authoring** is the gap. Strong conversion lever for the
  architect segment.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** A `.family.json` authoring UX where the user defines
  parameters → constraint-driven nested geometry, with a flex panel
  that exercises parameter sets. Extends the first-pass family editor
  (T-30) into a complete authoring surface.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/tools/
  family.py`, `src/cloud/` or `src/components/` family-editor UI,
  pytest + vitest.
- **Definition of Done:** a parametric column / window / door family
  authored end-to-end flexes correctly across parameter sets; vitest
  flex test; pytest schema.
- **Depends-on:** T-30

### T-110 BIM family library (curated catalog)
- **Tier:** A
- **Money/reach rationale:** Architect-persona depth — a populated
  family catalog is a cold-start killer once T-109 lands. Empty
  library = silent conversion killer.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Seed a curated parametric-family library across walls /
  doors / windows / structural sections / MEP fixtures using the same
  MIT-clean fetch/convert pattern as `kerf-parts`. Pinned, reproducible.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/library/`
  (new), seed scripts, tests with no committed third-party data.
- **Definition of Done:** the seed produces ≥1 valid family per
  category with provenance; pytest reproducible.
- **Depends-on:** T-109

### T-111 BIM walls / doors / windows / slabs full parametric
- **Tier:** A
- **Money/reach rationale:** Architect-persona depth. Today only basic
  primitives; Revit's full parametric envelope objects (compound walls
  with layers, parametric door / window types, sloped slabs) are the
  reference.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Promote the basic wall / door / window / slab primitives
  to fully parametric: compound layered walls, parametric door /
  window types with hardware, sloped + cranked slabs with edge profiles.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/`
  (walls.py, openings.py, slabs.py extensions), tests.
- **Definition of Done:** each parametric type flexes across a
  realistic parameter range and IFC-exports correctly; pytest.
- **Depends-on:** none

### T-112 BIM stairs / ramps full
- **Tier:** A
- **Money/reach rationale:** Architect-persona depth. Basic stairs
  shipped; full Revit-class stair / ramp authoring (multi-flight,
  winders, code-compliant rise / run, ramps with landings) is the gap.
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Multi-flight stair authoring with winders, code-compliant
  rise / run checks, monolithic + assembled construction; ramps with
  landings + handrails.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/stairs.py`
  (extension), tests.
- **Definition of Done:** a multi-flight U-stair + a ramp with two
  landings IFC-export correctly; pytest.
- **Depends-on:** none

### T-113 BIM structural grid + framing (Revit Structure / Robot / Tekla)
- **Tier:** A
- **Money/reach rationale:** Architect + structural-engineer depth
  (2 personas). Early today; the Revit Structure / Autodesk Robot /
  Tekla Structures class is the reference (axis grid + beam / column
  framing + connections + member rebar).
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** A `.grid` axis-grid primitive + framing layout that snaps
  beams / columns to grid intersections + connection nodes + rebar
  attachment. Reuses the shipped weldments member primitive where
  possible.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/`
  (grid.py, framing.py), tests.
- **Definition of Done:** a 3-bay × 2-storey frame snaps to a grid +
  IFC-exports correctly; pytest.
- **Depends-on:** none

### T-114 BIM site / earthwork (toposolids)
- **Tier:** A
- **Money/reach rationale:** Architect + civil persona depth
  (2 personas). Basic site only today; Revit toposolids + Civil 3D
  cut/fill is the reference. Bridges to the P3 civil seed (T-70).
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** A toposolid type from point cloud / TIN + cut/fill
  earthwork report. Reuses the T-70 civil TIN engine when present;
  standalone seed otherwise.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/`
  (site.py), bridge to `packages/kerf-civil/` once seeded, tests.
- **Definition of Done:** a TIN → toposolid + cut/fill volume report
  on a fixture site; pytest.
- **Depends-on:** none

### T-115 BIM material catalogue with render appearance
- **Tier:** A
- **Money/reach rationale:** Architect-persona presentation depth.
  Generic PBR shipped (this session), but no BIM-bound material library
  (Revit's "Materials with Appearance" / Enscape-class).
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** A `material.bim.json` catalogue with thermal / fire /
  acoustic + render-appearance (PBR map set + IOR) properties; tie
  each material to IFC `IfcMaterial` round-trip + the shipped PBR
  hero renderer.
- **Target files/packages:** `packages/kerf-bim/src/kerf_bim/
  materials.py` + seed catalogue, render-appearance wiring into
  `src/lib/heroShot.js` / `packages/kerf-render/`, tests.
- **Definition of Done:** a wall with a catalogued material renders
  via the PBR hero path + IFC round-trips its `IfcMaterial`; pytest.
- **Depends-on:** none
