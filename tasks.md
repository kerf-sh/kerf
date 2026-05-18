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
| 51 | **T-116** Text/code file plain-highlight | B | P0 cross-sector UX: every persona that edits `.py .js .ts .c .cpp .h .json .yaml .md` etc. in the file tree gets an editable plain-text view with basic syntax classes today; full language servers later. Zero-dependency, high-value signal; unblocks firmware + scripting personas. |
| 52 | **T-117** Phase-1 safety net — quota tests (kerf_free / kerf_paid / byo) | A | Platform correctness: billing quota enforcement is a revenue gate; tests must cover all three billing buckets before any launch. P0. |
| 53 | **T-118** Phase-1 safety net — billing collection with simulated clock | A | Platform correctness: billing collection logic was blocked by the missing `cloud_invoices` DDL (now fixed in 1c1127b); simulated-clock tests verify debit / invoice / grace-period state machine. P0. |
| 54 | **T-119** Phase-1 safety net — FX tests (USD display / ZAR settle) | A | Platform correctness: exchange-rate markup and currency display are revenue-critical; tests must catch drift. P0. |
| 55 | **T-120** Phase-1 safety net — API smoke suite | B | Platform health: a one-file hermetic smoke suite that hits the critical happy-path API endpoints (create project / file / chat / export) so a fresh DB + deploy is verified in <60 s. P0. |
| 56 | **T-121** Phase-1 safety net — security suite (IDOR / authz / token) | A | Platform correctness: IDOR, workspace authz cross-tenant, token single-use + expiry — table-stakes before any public launch. P0. |
| 57 | **T-122** Phase-1 safety net — harness + loop scripts (loop_local.sh / loop_dev.sh) | B | Platform correctness: one unified test harness that drives the Phase-1 suite locally and against a dev Neon DB; agents and CI both use it. P0. |
| 58 | **T-123** Export / materialize spine — file-tree materialization + large-file autodetect | A | P0/P1 foundational: the `GET /projects/{pid}/export` route already exists (~L3622); extend it to autodetect inline (`files.content`) vs stored (`files.storage_key`) files, emit a manifest, and produce a correct zip/tar. This is the single shared spine under sync / import / git. |
| 59 | **T-124** Git-as-substrate — content-vs-storage_key large-file autodetect + Tigris blob/pointer | A | P1 core: NOT valid UTF-8 OR size > ~1 MiB (configurable) → write blob to Tigris S3 (sha256-addressed), commit a tiny pointer file in git. Forks share blobs via content-addressed dedup. Extend the existing `files.content` / `files.storage_key` seam; do not add a new one. |
| 60 | **T-125** Git-as-substrate — shared server-side object store + cheap forks | A | P1 core: every cloud project is a hosted git repo; implement/wire the shared git object store so forked projects share large-file blobs with near-zero marginal storage. Standard `git clone` works: yields source + pointer stubs. |
| 61 | **T-126** Mode-agnostic client — `pip install kerf` + `kerf serve` self-host | B | P1 platform: `pip install kerf` = thin cloud client (KERF_API_URL default = cloud). `pip install 'kerf[server]'` + `kerf serve` = self-host. Self-host requires Postgres (documented BYO one-liner); `kerf serve` fails fast with a clear actionable error (prints the `docker run postgres` one-liner) when DATABASE_URL is missing or unreachable. No embedded/auto-provisioned Postgres. |
| 62 | **T-127** `kerf sync` — two-way folder mirror (cloud ↔ local) | A | P1 platform: `kerf sync <project-id> ./local-dir` — pull/push changed files between a cloud project and a local folder. Anti-lock-in pillar; builds on the T-123 materialize spine. |
| 63 | **T-128** `kerf export` / `kerf import` — zip/tar plain tree portability | B | P1 platform: `kerf export` emits a self-contained zip/tar of the project file tree (source + pointer stubs for large files); `kerf import` reconstitutes a project from such an archive. Symmetric cloud/local = anti-lock-in. Builds on T-123. |
| 64 | **T-129** Ladder logic / PLC — IEC 61131-3 LD editor (complements `plc_st`) | A | P2 sector depth: extends the existing `plc_st` (ST/MATIEC) kind to LD (Ladder Diagram) — the most widely used PLC language in manufacturing. Adds a ladder rung editor + MATIEC LD lint + IEC 61131-3 export. Unlocks the PLC/automation engineer segment. |
| 65 | **T-130** Embedded/firmware programming — broader extensions + PlatformIO-reference toolchain | A | P2 sector depth: `.ino`/`.uno` (Arduino), `.c`/`.cpp`/`.h` (general embedded), plus PlatformIO as the reference integration model (board manifest, build targets, upload/monitor). Complements T-116 (plain highlight) and T-129 (PLC). Unlocks the embedded/firmware engineer segment. |
| 66 | **T-131** Fully-local / offline desktop — PGlite WASM-Postgres spike + Tauri (P3, demand-gated) | B | P3 post-launch: spike PGlite (WASM Postgres) + a Tauri shell as the path to a fully-local/offline desktop app. **Explicitly NOT a launch pillar.** Only begin when there is validated demand signal; zero-dependency self-host (T-126) comes first. |
| 67 | **T-132** LFS-format blob pointer module + tests | B | P1 foundational: parse/serialize the standard 3-line Git-LFS pointer (`version`/`oid sha256:`/`size`) so large files commit as tiny pointers and a future real-LFS option stays trivial. Self-contained, zero-dependency; unblocks T-124. |
| 68 | **T-133** Large-file classifier + config threshold + tests | A | P1 foundational: the decided autodetect predicate — blob if size > 1 MiB (configurable) OR not valid UTF-8; **size dominates** (STEP is ASCII but huge). Pure function, sole owner of one new config setting; unblocks T-124. |
| 69 | **T-134** Blob object ledger schema — oid ref-count (sole migration owner) | A | P1 foundational: clean-baseline `blob_objects` + `blob_refs` for oid ref-counting; the shared dependency of dedup-billing (T-135) and GC (T-136). The ONLY storage task that touches migrations. |
| 70 | **T-135** Dedup billing attribution — design record | A | P1 revenue policy: decided model — the workspace that first uploads an oid bears its bytes; forks referencing an unchanged oid pay 0 ("forks are free"); Σ size by first-uploader into the existing GB-month meter. Design doc only. |
| 71 | **T-136** Large-object GC — design record | B | P1 platform safety: oid ref-count + git-history reachability + grace-window sweep worker; never deletes a blob reachable from any fork/commit. Design doc only. |
| 72 | **T-137** Vanilla-clone hydration UX — design record | B | P1 platform UX: bare `git clone` yields LFS-format stubs; documented next step `kerf hydrate`/`kerf pull-blobs`, and `kerf sync` hydrates implicitly. Design doc only. |

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
<!-- Status reconciled 2026-05-17 (this session's landings): T-100 picked
     up a reference-value suite (`pressure_load.py` + 43-test
     `test_fem_refvalues.py` with Roark/Blevins/Incropera oracles, 42
     green, one ASTM E1049 rainflow test skipped — bug flagged in
     `fatigue_fem._rainflow`); T-101 picked up `cfd_navier_stokes.py`
     (lid-driven cavity, Ghia Re=100 reference) on top of the
     pre-existing `cfd_potential.py`, 61 hermetic CFD tests in
     `test_cfd.py`. Both stay 🚧 in flight — full CalculiX/Z88/Mystran
     enum-wiring (T-100) and full CfdOF turbulence/3-D-mesh/OpenFOAM
     bridge (T-101) remain. T-106 split into T-106a..f for the Cycles
     backend + browser path-tracer fallback already in the body below;
     no new T-NN added — T-106f explicitly covers the
     `three-gpu-pathtracer` browser fallback. -->
<!-- Status reconciled 2026-05-18 (planning session — architecture decisions):
     Added T-116..T-131 for the directions resolved in the 2026-05-18
     planning session. Decisions captured:
     (1) Version-control substrate: every cloud project is a hosted git repo;
         files.content (small/textual/source) live in git; large/binary files
         AUTO-DETECTED via the existing files.content vs files.storage_key seam
         (predicate: NOT valid UTF-8 OR size > ~1 MiB configurable) → Tigris
         S3 sha256-addressed blob + pointer committed in git; forks share blobs
         (content-addressed dedup) + shared server-side git object store →
         near-zero-marginal-cost forks; standard git clone works.
         REJECTED: Git LFS (heavy ops/UX; our autodetect + shared object store
         already gives clone + cheap forks; LFS optional later only for
         pathological repos).
     (2) Install/runtime: one mode-agnostic client; ONLY difference is
         KERF_API_URL+token. pip install kerf = thin client defaults to cloud.
         pip install 'kerf[server]' + kerf serve = self-host; Postgres REQUIRED
         and NOT embedded/auto-provisioned; kerf serve fails fast with the BYO
         docker one-liner when DATABASE_URL is missing/unreachable.
         REJECTED: SQLite for local (forks SQL dialect forever); embedded/
         auto-provisioned Postgres (unnecessary + cross-platform maintenance
         liability); Electron bundling server+Postgres (hides infra).
     (3) Local sync + portability: kerf sync (two-way folder mirror), kerf
         export / kerf import (zip/tar plain tree), symmetric cloud/local =
         anti-lock-in. GET /projects/{pid}/export (~L3622) already exists —
         extend, don't duplicate; materialize spine is the foundational layer.
     In-flight state captured:
     - dc2f2e4 docs viewer fix (flattenManifest dropped article bodies) ✅
     - 1c1127b billing schema fix (cloud_invoices + cloud_debit_balance()
       missing from ALL migrations; folded into 0008 baseline) ✅
       NOTE: dev Neon schema must be drop+recreated on next deploy.
     - Phase-1 safety net 🚧 paused: (1) docs bug ✅; (2) seed_dev.py paused;
       (3) quota tests T-117; (4) billing collection T-118; (5) FX tests T-119;
       (6) API smoke T-120; (7) security suite T-121; (8) harness T-122.
     New tasks:
     T-116 text/code plain-highlight P0 🔴;
     T-117 quota tests P0 🔴; T-118 billing collection/clock P0 🔴;
     T-119 FX tests P0 🔴; T-120 API smoke P0 🔴; T-121 security suite P0 🔴;
     T-122 harness+loop scripts P0 🔴;
     T-123 export/materialize spine P0 🔴;
     T-124 git-as-substrate large-file autodetect+Tigris blob P1 🔴;
     T-125 git-as-substrate shared object store+cheap forks P1 🔴;
     T-126 mode-agnostic client pip install P1 🔴;
     T-127 kerf sync two-way mirror P1 🔴;
     T-128 kerf export/import zip/tar P1 🔴;
     T-129 ladder logic / PLC IEC 61131-3 LD P2 🔴;
     T-130 embedded/firmware + PlatformIO toolchain P2 🔴;
     T-131 fully-local desktop PGlite+Tauri P3 🔴. -->

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
- **Status:** ✅ shipped
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
- **Status:** ✅ shipped
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (already landed pre-session at 1360b6a; marker reconciled)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** 🚧 in flight — **reference-value suite landed
  (2026-05-17):** `kerf_fem.pressure_load` + 43-test
  `packages/kerf-fem/tests/test_fem_refvalues.py` with citable Roark /
  Blevins / Incropera oracles, 42 green, one ASTM E1049 rainflow test
  skipped (real bug flagged in `fatigue_fem._rainflow`, ranked
  alongside the remaining enum-wiring work). Public `analysis_type`
  enum-wiring + CalculiX / Z88 / Mystran reference-tool match still
  ahead.
- **Scope:** Wire the seed nonlinear / explicit / acoustics / EM /
  fatigue modules through the public analysis enum + LLM tool surface,
  then match a CalculiX (nonlinear / contact) + Z88 (linear / modal /
  nonlinear) + Mystran (modal / aeroelastic) reference test corpus.
  **Remaining sub-items after the 2026-05-17 landings:**
  - fix `fatigue_fem._rainflow` (ASTM E1049) — currently skipped
  - wire `nonlinear` / `explicit` / `acoustics_fem` / `em_field` /
    `em_highfreq` / `fatigue_fem` through `tools.py` analysis-enum
  - publish the new capability tags on `GET /health/capabilities`
  - extend the 43-test `test_fem_refvalues.py` corpus with
    CalculiX / Z88 / Mystran match-cases.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/` (`tools.py`
  analysis-enum extension, plugin capability advertisements,
  `nonlinear.py` / `explicit.py` / `acoustics_fem.py` / `em_field.py` /
  `em_highfreq.py` / `fatigue_fem.py`, `pressure_load.py`), reference-
  test corpus under `packages/kerf-fem/tests/` (already-shipped
  `test_fem_refvalues.py` is the seed).
- **Definition of Done:** each module passes its reference-tool match
  within tolerance; analysis-enum advertises the new types; capability
  tags appear in `GET /health/capabilities`; rainflow bug fixed and
  the skipped test re-enabled.
- **Depends-on:** none

### T-101 CFD CfdOF-class — turbulence + 3-D meshing + OpenFOAM bridge
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive + aerospace
  simulation depth (3 personas, P2 — moat depth not P0 unlock). Potential
  flow (`cfd_potential.py`) is the seed already in flight; full CfdOF
  parity is engine-class.
- **Priority:** P2
- **Status:** 🚧 in flight — **2-D laminar foundation landed
  (2026-05-17):** `kerf_fem.cfd_potential` (potential flow,
  `Cp(θ) = 1 − 4 sin²θ` analytic oracle) + `kerf_fem.cfd_navier_stokes`
  (lid-driven cavity, Ghia Re=100 reference); 61 hermetic CFD tests in
  `packages/kerf-fem/tests/test_cfd.py`. Lid-driven cavity NS
  reference-tolerance match shipped; turbulence (k-ε / k-ω SST), 3-D
  unstructured meshing, and the OpenFOAM bridge all still ahead.
- **Scope:** Extend `cfd_potential.py` + `cfd_navier_stokes.py` past
  the 2-D laminar foundation into full Navier-Stokes + heat transfer
  with turbulence models (k-ε / k-ω SST), 3-D unstructured meshing,
  and an OpenFOAM bridge for the serious-CFD path (graceful degrade
  when the binary is absent, same pattern as CuraEngine /
  Instant-Meshes). **Remaining sub-items after the 2026-05-17
  landings:**
  - k-ε / k-ω SST turbulence models with the standard test cases
  - 3-D unstructured mesh path (`packages/kerf-fem/src/kerf_fem/mesh3d.py`
    or similar)
  - `openfoam_bridge.py` — case-translate + subprocess + result-parse,
    sentinel-degrade when the binary is absent.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_*.py`,
  optional `packages/kerf-fem/src/kerf_fem/openfoam_bridge.py`, tests
  (already-shipped `test_cfd.py` is the seed).
- **Definition of Done:** turbulence model toggle works and matches a
  canonical reference case (channel flow / backward-facing step);
  OpenFOAM bridge round-trips a fixture case with binary present →
  degrades to sentinel when absent; 3-D unstructured mesh on a
  fixture geometry.
- **Depends-on:** none

### T-102 ECAD: interactive push-and-shove diff-pair routing
- **Tier:** A
- **Money/reach rationale:** ECAD-persona depth — KiCad has interactive
  push-and-shove; Kerf has length tuning only. A visible UX-class quality
  signal that converts ECAD evaluators after the fab-output unlock.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (already landed pre-session 474de59/63a406d/6496bd1; reconciled)
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
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Author-time SubD: create from primitives or convert from
  mesh; edge / vertex / face edit ops with crease weights; round-trip
  to the existing Catmull-Clark evaluator; UX surface.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/subd.py` (authoring API extensions), worker handler, tests, UX.
- **Definition of Done:** create-edit-evaluate round-trips on a SubD
  cube + cylinder; creases hold under subdivision; vitest dispatch +
  pytest math.
- **Depends-on:** none

### T-106 Render: caustics + dispersion solver (epic — split into T-106a..f)
- **Tier:** B
- **Money/reach rationale:** Cross-sector presentation depth — jewelry
  (gem dispersion is the deliverable), automotive (paint / glass
  caustics), architecture (Enscape-class daylighting). PBR + HDRI +
  bloom shipped this session; the next-class jump is a real caustic
  transport solver. Browser path-tracer alone won't cover every
  customer's GPU; we need a backend render path with hybrid fallback.
- **Priority:** P2
- **Status:** 🔴 not started (broken into sub-tasks T-106a..f below)
- **Scope:** End-to-end backend render via headless Blender Cycles
  (primary; spectral dispersion shipped in 4.0+), with in-browser
  `three-gpu-pathtracer` as the free-preview / offline fallback.
- **Target files/packages:** `packages/kerf-render/src/kerf_render/`
  (worker + scene-translation), `src/lib/heroShot.js` (browser
  fallback), `src/components/Renderer.jsx` (panel UI), cloud
  worker pool + billing.
- **Definition of Done:** rolled up from T-106a..f.
- **Depends-on:** none

### T-106a Scene translator + materials mapping (Kerf Body → Blender Cycles)
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (already landed pre-session bf1b4be/2b17161/5f8ffe1; reconciled)
- **Scope:** Translate a Kerf scene (Body topology + camera + lights +
  materials) into Blender format. Path: export Kerf Body via glTF →
  import in Blender via `bpy.ops.import_scene.gltf` → map Kerf PBR
  materials (gold / silver / platinum / diamond / sapphire / etc.) to
  Blender Principled BSDF; gemstones use Glass BSDF with spectral
  dispersion + Abbe-number lookup from `jewelry/gemstones.py`.
- **Target files/packages:**
  `packages/kerf-render/src/kerf_render/cycles_translator.py`,
  `packages/kerf-render/src/kerf_render/material_mapping.py`,
  reference tests with synthetic scenes.
- **Definition of Done:** round-trip a known ring scene (diamond +
  18k yellow shank) → Cycles renders match a baseline reference
  image within delta-E tolerance; spectral dispersion produces a
  chromatic fan on the table beneath the stone.
- **Depends-on:** none (glTF interop already shipped)
- **Suggested model tier:** opus

### T-106b Cycles worker (subprocess harness + job lifecycle + cache)
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (code pre-landed; stale migration test reconciled this session)
- **Scope:** Worker process that consumes render jobs from the Postgres
  queue, drives `bpy` in an isolated subprocess (so a crash doesn't
  take the harness down), streams tile progress via SSE/WebSocket,
  writes PNG + multi-pass EXR to object storage, caches by
  `sha256(scene_blob + preset + renderer_version)`.
- **Target files/packages:**
  `packages/kerf-render/src/kerf_render/cycles_worker.py`,
  `packages/kerf-workers/` integration, Postgres migration for a
  `render_jobs` table, `kerf_api.routes` job endpoints.
- **Definition of Done:** queue → render → cache → signed-URL
  download works end-to-end on a single worker; identical scene
  hash returns cached result instantly; pytest gated on a fake-bpy
  harness.
- **Depends-on:** T-106a
- **Suggested model tier:** opus

### T-106c Hero-render UX panel (browser-side)
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Viewport "Hero Render" button + quality picker
  (Draft 256 / Standard 1024 / Hero 4096 / Cinema 16384 samples),
  progress bar with tile preview streaming, PNG + EXR download,
  gallery tab listing past renders for the current project.
- **Target files/packages:** `src/components/Renderer.jsx`
  (button + state), new `src/components/HeroRenderPanel.jsx`,
  `src/lib/heroShot.js` (extend to call backend job API),
  `src/routes/Projects.jsx` (gallery tab).
- **Definition of Done:** submit a Hero render from the viewport,
  watch progress, download PNG + EXR; vitest renders the panel
  with mocked job state.
- **Depends-on:** T-106b
- **Suggested model tier:** sonnet

### T-106d Pricing meter (GPU-seconds → kerf_paid credits)
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Wire the cycles_worker's GPU-seconds consumption into
  `kerf-billing` as a metered draw against `kerf_paid` credits.
  Quality presets map to credit costs (Draft ≈ 0.5 / Standard ≈ 2 /
  Hero ≈ 10 / Cinema ≈ 60). Free quota: ~3 Hero renders / month on
  the Studio tier. Cache hits are free.
- **Target files/packages:** `packages/kerf-billing/src/kerf_billing/`
  (new meter), `packages/kerf-pricing/` (preset credit prices),
  `kerf-cloud` billing wire.
- **Definition of Done:** running a Hero render against a non-cached
  scene decrements the user's kerf_paid balance by the documented
  amount; cache hit is zero-cost; rejection if balance < cost.
- **Depends-on:** T-106b
- **Suggested model tier:** sonnet

### T-106e Self-host docker image + BYO Blender path
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Containerised `cycles-worker` (Dockerfile + entrypoint)
  so a self-hosted user runs the worker on their own GPU box (no
  cloud bill). Plus a BYO-Blender alternative where the user points
  `KERF_BLENDER_PATH` at their existing Blender install. Document
  both paths in `docs/local-self-host.md`.
- **Target files/packages:**
  `packages/kerf-render/Dockerfile.cycles-worker`,
  `packages/kerf-render/entrypoint.sh`,
  `docs/local-self-host.md` (extend),
  `docs/cloud-features.md` (clarify the cloud-vs-local split).
- **Definition of Done:** docker image builds and runs against a
  local kerf-server; BYO path picks up installed Blender and
  dispatches a render synchronously.
- **Depends-on:** T-106b
- **Suggested model tier:** sonnet

### T-106f In-browser path-tracer fallback (`three-gpu-pathtracer`)
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Integrate the MIT-licensed `three-gpu-pathtracer` into
  `src/lib/heroShot.js` as a fallback / free preview path. Reuses
  the existing scene graph + PMREM HDRI + ACES tonemap. Progressive
  rendering on the user's GPU; gives caustics + dispersion + SSS
  in-browser without server compute. Ships as the free preview tier
  AND the offline / no-cloud fallback for self-host users without
  a GPU box.
- **Target files/packages:** `src/lib/heroShot.js` (extend),
  `src/components/Renderer.jsx` (toggle), `package.json`
  (`three-gpu-pathtracer` dep — first new npm dep this session;
  acceptable because it closes the killer jewelry gap).
- **Definition of Done:** clicking the Hero button in offline mode
  (or for free-tier users) progressively renders the scene in the
  browser; diamond + table demonstrates caustics + dispersion
  visually; vitest sanity-renders a low-sample frame in headless
  mode.
- **Depends-on:** T-106a (reuses material mapping)
- **Suggested model tier:** opus

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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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

---

## Phase-1 safety net + platform infrastructure (T-116 … T-128)

Tasks surfaced in the 2026-05-18 planning session. P0 items (T-116..T-123)
unblock safe launch and correct billing; P1 items (T-124..T-128) build the
version-control + install + sync platform spine. Decisions and rejections
are captured in the 2026-05-18 status comment above.

### T-116 Text/code file plain-highlight (editable viewer for common extensions)
- **Tier:** B
- **Money/reach rationale:** Every persona that touches source code,
  config, or documentation files benefits — firmware engineers
  (`.c .cpp .h .ino`), electronics (`.json .yaml`), scripting
  (`.py .js .ts`), BIM (`.md`), and plain text everywhere. Zero
  dependency (CSS class tokens only for now); highest cross-persona
  breadth per unit of effort. Unblocks the firmware/embedded segment
  as a readable first step.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** In the file editor / viewer, detect files whose `kind` or
  extension matches the plain-highlight set (`.txt .md .c .cpp .h .hpp
  .py .js .ts .json .yaml .yml .toml .ini .cfg .sh .ino .uno .ld .v
  .vhd` and similar) and render them as editable plain text with a
  lightweight syntax-class tokenizer (no LSP, no WASM). The UI should
  show a CodeMirror or equivalent plain editor with basic token
  colouring; full language intelligence (LSP) is a later task.
  **Decision:** plain highlighting now; per-language syntax servers
  later.
- **Target files/packages:** `src/components/FileEditor.jsx` (or the
  relevant editor component), extension→mode mapping table in
  `src/lib/editorModes.js` (new or extend existing), a lightweight
  tokenizer import (e.g. `@codemirror/lang-*` basic packs already in
  the bundle or a pure-regex fallback), `src/__tests__/` vitest.
- **Definition of Done:** opening a `.py`, `.c`, `.json`, `.md`, and
  `.sh` file in the editor shows coloured tokens (at minimum: keywords,
  strings, comments); the file is editable and round-trips through the
  existing save path; no new WASM dependency; vitest asserting the
  extension→mode mapping covers every listed extension.
- **Depends-on:** none

### T-117 Phase-1 safety net — quota tests (kerf_free / kerf_paid / byo)
- **Tier:** A
- **Money/reach rationale:** Billing quota enforcement is a direct
  revenue gate — a quota bug lets free users consume paid resources
  or blocks paying users. Affects all cloud personas. P0 platform
  correctness.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Hermetic pytest suite covering all three billing buckets:
  `kerf_free` (cheap-models-only enforcement), `kerf_paid` (credits,
  any model, debit path), `byo` (own key, zero billing, no quota
  check). Each bucket gets a request-dispatch test asserting the
  correct quota response. Use the existing fake-pool pattern; no live
  model calls.
- **Target files/packages:** `packages/kerf-billing/tests/
  test_quota.py` (new), `packages/kerf-billing/src/kerf_billing/
  buckets.py` (extend if needed), `packages/kerf-chat/src/
  kerf_chat/` (LLM dispatch path quota gate).
- **Definition of Done:** `kerf_free` request for a non-cheap model
  returns the quota sentinel; `kerf_paid` request for any model
  decrements credits and returns success; `byo` request bypasses
  billing and returns success; all three green in CI with no live
  calls.
- **Depends-on:** none

### T-118 Phase-1 safety net — billing collection with simulated clock
- **Tier:** A
- **Money/reach rationale:** Billing collection correctness is a hard
  revenue requirement — missed or double-collected invoices directly
  hit revenue. Blocked previously by the missing `cloud_invoices` DDL
  (fixed in commit 1c1127b); that fix is now in HEAD.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Pytest suite for the billing collection state machine
  using a simulated wall clock: advance the clock through billing
  cycle boundaries and assert that `cloud_invoices` rows are created,
  `cloud_debit_balance()` is decremented, grace-period transitions
  fire correctly, and a zero-balance account is suspended at the right
  moment. Fake-pool; no live Stripe/Paystack calls.
- **Target files/packages:** `packages/kerf-billing/tests/
  test_collection.py` (new), `packages/kerf-billing/src/kerf_billing/
  collection.py` (billing collection logic), `packages/kerf-cloud/
  src/kerf_cloud/` (cloud billing wire),
  `packages/kerf-core/src/kerf_core/db/migrations/0008_*.sql`
  (baseline now contains `cloud_invoices` + `cloud_debit_balance()`).
- **Definition of Done:** debit/invoice/grace/suspend state machine
  transitions verified at T+0, T+billing_interval, T+grace_end;
  `cloud_debit_balance()` matches expected value at each step; all
  green in CI with no live payment-processor calls.
- **Depends-on:** none

### T-119 Phase-1 safety net — FX tests (USD display / ZAR settle)
- **Tier:** A
- **Money/reach rationale:** USD-display / ZAR-settle with a 20% FX
  markup is the live pricing model; a silent FX drift bug directly
  loses or overcharges revenue. P0 platform correctness.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Hermetic pytest suite asserting: (a) the USD→ZAR
  conversion applies the documented 20% markup correctly; (b) display
  amounts are always in USD regardless of settlement currency; (c) the
  FX rate lookup degrades gracefully (cached fallback) when the rate
  API is unreachable; (d) rounding is deterministic (no floating-point
  drift across Python versions).
- **Target files/packages:** `packages/kerf-billing/tests/test_fx.py`
  (new), `packages/kerf-billing/src/kerf_billing/fx.py` (FX logic),
  pinned fixture exchange-rate for hermetic tests.
- **Definition of Done:** all four assertions green; FX rate API
  mocked (no live HTTP); no floating-point drift on the pinned
  fixture.
- **Depends-on:** none

### T-120 Phase-1 safety net — API smoke suite
- **Tier:** B
- **Money/reach rationale:** A broken happy-path (create project /
  upload file / send chat / export) silently kills every persona's
  experience before anyone notices. One fast hermetic smoke suite
  catches regressions on any fresh deploy. Cross-sector platform
  health.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** A single-file pytest smoke suite
  (`packages/kerf-api/tests/test_smoke.py`) that hits the critical
  happy-path endpoints in order: bootstrap-local auth → create
  workspace → create project → create file → list files → send chat
  message (mocked LLM) → GET /projects/{pid}/export. Uses the
  existing test-app fixture; no live cloud, no live LLM. Must
  complete in under 60 seconds.
- **Target files/packages:** `packages/kerf-api/tests/test_smoke.py`
  (new), existing `conftest.py` app fixture.
- **Definition of Done:** all seven smoke steps green; LLM mocked;
  export returns a valid zip with at least one file; full suite runs
  in < 60 s.
- **Depends-on:** none

### T-121 Phase-1 safety net — security suite (IDOR / authz / token)
- **Tier:** A
- **Money/reach rationale:** IDOR and cross-tenant authz failures are
  table-stakes security for any SaaS — a single exploit here is a
  company-ending event before launch. Token single-use + expiry are
  required by the auth spec (password-reset tokens in particular).
  Affects every cloud persona.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Hermetic pytest security suite covering: (a) IDOR — user
  A cannot GET/PUT/DELETE user B's project, file, or workspace; (b)
  cross-workspace authz — workspace member cannot access a project in
  a different workspace; (c) token single-use — a used password-reset
  / email-verification token is rejected on a second use; (d) token
  expiry — an expired token is rejected; (e) bootstrap-local auth is
  blocked in cloud mode.
- **Target files/packages:** `packages/kerf-api/tests/
  test_security.py` (new), existing auth / project / workspace routes
  in `packages/kerf-api/src/kerf_api/routes.py`.
- **Definition of Done:** all five assertion categories green in CI;
  each negative case returns the expected 403/404 (not a 500); no
  live external calls.
- **Depends-on:** none

### T-122 Phase-1 safety net — harness + loop_local.sh / loop_dev.sh
- **Tier:** B
- **Money/reach rationale:** A unified test harness that any agent or
  CI job can invoke is a force-multiplier for the entire Phase-1
  safety-net suite — without it, the individual tests pass in
  isolation but regressions slip through on real deploys. Cross-
  sector platform health.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Two thin shell scripts:
  `scripts/loop_local.sh` — runs the full Phase-1 suite (T-117..T-121
  + T-120 smoke) against a local Postgres (`postgres://pc@localhost:
  5432/kerf?sslmode=disable` or `DATABASE_URL` env override);
  `scripts/loop_dev.sh` — same suite against the dev Neon URL from
  `KERF_DEV_DATABASE_URL`. Both scripts: set up a clean schema (drop +
  recreate via `0008` baseline migration), run pytest with the
  relevant test globs, print a pass/fail summary. Neither script
  commits data or mutates prod.
- **Target files/packages:** `scripts/loop_local.sh` (new),
  `scripts/loop_dev.sh` (new), `packages/kerf-api/tests/conftest.py`
  (extend DB-URL injection if needed).
- **Definition of Done:** `./scripts/loop_local.sh` runs cleanly on a
  fresh local DB and prints PASS for all Phase-1 tests; `loop_dev.sh`
  parameterises the DB URL without hardcoding; both scripts are
  executable and documented with a one-line usage comment at the top.
- **Depends-on:** T-117, T-118, T-119, T-120, T-121

### T-123 Export / materialize spine — file-tree materialization + large-file autodetect
- **Tier:** A
- **Money/reach rationale:** The export/materialize spine is the
  shared foundation under `kerf sync`, `kerf export`/`kerf import`,
  and git-as-substrate (T-124, T-125, T-127, T-128). Without it each
  of those builds its own ad-hoc file-tree walk. Gets anti-lock-in
  correct once, reused by every platform persona. P0 foundational.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Extend the existing `GET /projects/{pid}/export` route
  (≈L3622 in `packages/kerf-api/src/kerf_api/routes.py`) — do NOT
  create a duplicate route — to: (a) autodetect inline vs stored files
  via the existing `files.content` / `files.storage_key` seam:
  `files.content` is present → inline, served directly; `files.
  storage_key` is set → fetch from Tigris, include in zip; (b) emit a
  `manifest.json` inside the zip listing each file's path, kind,
  sha256, and whether it was inline or storage-keyed; (c) handle the
  500MB cap that already exists. The large-file autodetect predicate
  (NOT valid UTF-8 OR size > ~1 MiB) is implemented here as a helper
  used by the write path too — the same predicate gates T-124.
- **Target files/packages:**
  `packages/kerf-api/src/kerf_api/routes.py` (extend
  `export_project` ≈L3622), new helper
  `packages/kerf-api/src/kerf_api/export_helpers.py` (autodetect
  predicate + manifest builder), `packages/kerf-api/tests/
  test_export.py` (extend or new).
- **Definition of Done:** exporting a project with a mix of inline
  and storage-keyed files produces a zip containing: all inline files
  at their correct paths, pointer stubs for storage-keyed files,
  and a valid `manifest.json`; the autodetect predicate correctly
  classifies a UTF-8 text file, a >1 MiB binary, and a <1 MiB binary;
  pytest green; existing export tests still green.
- **Depends-on:** none

### T-124 Git-as-substrate — content-vs-storage_key large-file autodetect + Tigris blob/pointer
- **Tier:** A
- **Money/reach rationale:** The auto-detection mechanism is what
  makes every cloud project a true git repo without manual LFS
  configuration — critical for the mechanical/ECAD/BIM personas whose
  projects contain large STEP / binary files alongside source code.
  Enables standard `git clone` to work. P1 platform spine. **Rejected
  alternative:** Git LFS — heavy ops/UX; our autodetect + shared
  object store already gives standard clone + cheap forks; LFS is
  optional later only for pathological repos.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** On every file write/commit, run the autodetect predicate
  from T-123 (NOT valid UTF-8 OR size > ~1 MiB configurable via
  `KERF_LARGE_FILE_THRESHOLD_BYTES` env, default 1 MiB). If large:
  compute sha256, write content to Tigris S3 under
  `blobs/{sha256[:2]}/{sha256}` (content-addressed, idempotent),
  set `files.storage_key = sha256`, commit a pointer file
  `{filename}.kerf-ptr` in git containing `kerf-ptr v1\nsha256:
  {sha256}\nsize:{n}\n`. If small: write content inline, commit the
  file directly. The pointer format is intentionally minimal and
  human-readable. Forks share blobs automatically (same sha256 →
  same Tigris key).
- **Target files/packages:** `packages/kerf-api/src/kerf_api/
  routes.py` (file-write path), `packages/kerf-api/src/kerf_api/
  export_helpers.py` (T-123 autodetect predicate — reuse), new
  `packages/kerf-cloud/src/kerf_cloud/blob_store.py` (Tigris write/
  read), `packages/kerf-core/src/kerf_core/db/migrations/` (add
  `content_sha256` column to `files` if not present), tests.
- **Definition of Done:** writing a >1 MiB binary file → `storage_key`
  set, blob in Tigris, pointer committed in git; writing a small UTF-8
  file → `files.content` set, file committed directly; round-trip
  (write → export via T-123 → verify content) passes; dedup verified
  (same content written twice → one Tigris object); pytest with a
  mocked Tigris client.
- **Depends-on:** T-123

### T-125 Git-as-substrate — shared server-side object store + cheap forks + `git clone` interop
- **Tier:** A
- **Money/reach rationale:** Cheap forks (near-zero marginal storage
  for the second and Nth fork of a project with large STEP files) are
  the core commercial proposition of the platform's version-control
  layer. Standard `git clone` working is a table-stakes requirement
  for any developer-facing CAD platform.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Wire the shared server-side git object store (the cloud
  git Storer already exists — see MEMORY cloud_git_storer_motivation)
  so that when a project is forked the new git repo shares pack
  objects with the original rather than duplicating them. On `git
  clone`, the server serves source files directly and pointer stubs
  for large files (the pointer content from T-124); a `kerf sync` or
  `kerf export --hydrate` step fetches the large-file blobs from
  Tigris. Document the clone + hydrate workflow in
  `docs/llm/git.md`.
- **Target files/packages:** `packages/kerf-cloud/src/kerf_cloud/
  git_storer.py` (extend fork path to share object store),
  `packages/kerf-api/src/kerf_api/routes.py` (fork endpoint),
  `docs/llm/git.md` (extend with clone + hydrate workflow), tests.
- **Definition of Done:** forking a project with a large-file pointer
  does not copy the Tigris blob (dedup verified by blob-store mock);
  `git clone` of the project repo yields source files + pointer stubs;
  a `kerf export --hydrate` on the clone directory resolves the
  pointers to their full content; pytest.
- **Depends-on:** T-124

### T-126 Mode-agnostic client — `pip install kerf` (cloud default) + `kerf serve` self-host (Postgres-required)
- **Tier:** B
- **Money/reach rationale:** A clean pip install story is the primary
  acquisition funnel for every non-browser persona (scripting, SDK,
  self-hosted enterprise). Self-host with a well-documented BYO-
  Postgres path unlocks the on-premise / air-gapped segment with
  zero marginal infrastructure cost. **Rejected alternatives:**
  SQLite for local (forks the SQL dialect forever); embedded/auto-
  provisioned Postgres (unnecessary + cross-platform maintenance
  liability); Electron bundling server+Postgres (hides infra).
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Restructure the Python package so: `pip install kerf`
  installs the thin client (no server deps, `KERF_API_URL` defaults
  to `https://app.kerf.io`); `pip install 'kerf[server]'` installs
  the full server extras (FastAPI, asyncpg, all plugin packages);
  `kerf serve` starts the server and **fails fast** with a clear
  actionable error message — printing the exact `docker run postgres`
  one-liner — when `DATABASE_URL` is missing or unreachable. The
  error message must be actionable without reading the docs. No
  embedded or auto-provisioned Postgres. Document the self-host
  path in `docs/local-self-host.md` (extend existing).
- **Target files/packages:** `packages/kerf-server/pyproject.toml`
  or the root `pyproject.toml` (optional `[server]` extra),
  `packages/kerf-server/src/kerf_server/cli.py` (`kerf serve` entry
  point + startup check), `docs/local-self-host.md` (extend),
  pytest for the startup-failure message.
- **Definition of Done:** `pip install kerf` succeeds with no server
  deps installed; `kerf serve` with no `DATABASE_URL` prints the
  docker one-liner error and exits non-zero; `kerf serve` with a
  valid `DATABASE_URL` starts and passes the T-120 smoke suite;
  self-host docs are accurate and complete; pytest for the error
  path.
- **Depends-on:** T-120

### T-127 `kerf sync` — two-way folder mirror (cloud ↔ local)
- **Tier:** A
- **Money/reach rationale:** Two-way sync is the primary anti-lock-in
  guarantee for professional personas (mechanical engineers, architects,
  firmware engineers) who work locally in their existing toolchain and
  want cloud backup / collaboration. It is the most direct answer to
  "can I get my files out?" — which is the single biggest objection
  to any SaaS CAD tool.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** `kerf sync <project-id> <local-dir>` — pull changed
  files from the cloud project to the local directory and push local
  changes back up. Change detection: server-side `updated_at` vs
  local mtime; conflict resolution: last-write-wins with a `--dry-run`
  flag that prints the diff without applying. Large files are
  handled via the T-124 pointer mechanism: pulling a pointer file
  triggers a Tigris fetch; pushing a large file triggers the T-124
  blob write. Builds directly on the T-123 materialize spine.
- **Target files/packages:** `packages/kerf-server/src/kerf_server/
  cli.py` (new `sync` subcommand), `packages/kerf-api/src/kerf_api/
  routes.py` (add `GET /projects/{pid}/files/changed-since?ts=` or
  extend the list-files endpoint), new `packages/kerf-server/src/
  kerf_server/sync.py` (sync engine), tests.
- **Definition of Done:** `kerf sync` pulls a new file created in
  the cloud to the local dir; pushes a locally-created file to the
  cloud; `--dry-run` prints the diff without mutating either side;
  a file deleted locally is not automatically deleted on the server
  (safe default, warn only); large-file pointer round-trips via T-124;
  pytest + integration test against the test-app fixture.
- **Depends-on:** T-123, T-124

### T-128 `kerf export` / `kerf import` — zip/tar plain-tree portability
- **Tier:** B
- **Money/reach rationale:** The export/import symmetry is the final
  anti-lock-in pillar — a user can always extract a complete plain-
  file-tree archive of their project, carry it elsewhere, or
  reconstitute it on a different Kerf instance. Low effort (builds on
  T-123). Needed by every persona who values data portability.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** `kerf export <project-id> [--output file.zip]` — calls
  the T-123 export route and writes the zip/tar to disk; `kerf import
  <file.zip> [--project-name name]` — POST the archive to
  `POST /projects/import` (new route) which unpacks the manifest,
  creates the project, writes each file (large files auto-detected via
  T-124 predicate and stored to Tigris). Both commands work in cloud
  mode (`KERF_API_URL` = cloud) and self-host mode.
- **Target files/packages:** `packages/kerf-server/src/kerf_server/
  cli.py` (new `export` + `import` subcommands), `packages/kerf-api/
  src/kerf_api/routes.py` (new `POST /projects/import`), tests.
- **Definition of Done:** `kerf export` produces a zip that contains
  all source files + pointer stubs + manifest.json; `kerf import` of
  that zip reconstitutes the project with all files present; a round-
  trip export → import produces identical file content; pytest.
- **Depends-on:** T-123, T-124

---

## Sector depth — embedded/firmware + PLC (T-129 … T-130)

### T-129 Ladder logic / PLC — IEC 61131-3 LD editor (complements `plc_st`)
- **Tier:** A
- **Money/reach rationale:** PLC / automation engineers are a large
  manufacturing-sector workforce. The existing `plc_st` kind covers
  IEC 61131-3 Structured Text; Ladder Diagram (LD) is the dominant
  language on the shop floor (Siemens, Allen-Bradley, Omron).
  Adding LD completes the IEC 61131-3 authoring story and unlocks the
  automation/OT segment. Complements, does not replace, `plc_st`.
- **Priority:** P2
- **Status:** ✅ shipped (integrated this session)
- **Scope:** A new `plc_ld` file kind with: a rung-based text schema
  (contacts, coils, timers, counters, function blocks as JSON/YAML);
  a SVG-based ladder viewer/editor (rungs rendered as the standard LD
  symbol set); MATIEC LD lint (MATIEC already used for ST); IEC
  61131-3 XML export (`*.xwl` or IEC-compliant XML). LLM tool
  `create_ladder_rung` + doc.
- **Target files/packages:** `packages/kerf-plc/src/kerf_plc/ld/`
  (new: `schema.py`, `renderer.py`, `lint.py`, `export.py`),
  `src/components/` (new `LadderView.jsx` or extend PLCView),
  migration for `plc_ld` kind,
  `packages/kerf-plc/llm_docs/ladder.md`.
- **Definition of Done:** a fixture LD program with a normally-open
  contact + timer + coil renders correctly as SVG rungs; MATIEC lint
  passes on a valid rung and catches a wiring error; IEC XML export
  round-trips; LLM tool creates a new rung given a text description;
  pytest + vitest.
- **Depends-on:** none

### T-130 Embedded/firmware programming — broader extensions + PlatformIO-reference toolchain
- **Tier:** A
- **Money/reach rationale:** Embedded/firmware engineers are a large
  workforce (IoT, industrial, automotive ECU, consumer electronics).
  T-116 gives them a readable editor; this task gives them a build +
  flash + monitor loop. PlatformIO is the reference model: board
  manifest, multi-framework support (Arduino, ESP-IDF, Zephyr, Mbed),
  build targets, serial monitor. Unlocks the embedded/firmware
  engineer persona end-to-end.
- **Priority:** P2
- **Status:** ✅ shipped (T-130)
- **Scope:** Introduce a `firmware` project type (or extend the
  existing scripting path) with: a `platformio.ini`-compatible board
  manifest (`boards.json`); a `build_firmware` LLM tool that invokes
  PlatformIO Core CLI (graceful degrade when absent — same pattern as
  CuraEngine); a serial monitor UI for flash + monitor; a dependency
  on T-116 (plain highlight covers `.ino .cpp .h .c`). PlatformIO Core
  CLI is invoked as a subprocess; the tool degrades to a
  "install PlatformIO" hint when the binary is absent.
- **Target files/packages:** new `packages/kerf-firmware/` (or
  extend `packages/kerf-scripting/`): `build.py`, `boards.py`,
  `monitor.py`; `src/components/FirmwareView.jsx` (build log + serial
  monitor panel); `packages/kerf-chat/llm_docs/firmware.md`;
  migration for `firmware` kind.
- **Definition of Done:** a fixture Arduino Blink sketch (`main.ino`)
  is compiled via PlatformIO Core CLI (binary present in CI or mocked)
  and produces an ELF + hex artefact; the build log streams to the
  FirmwareView panel; binary absent → sentinel + install-hint printed;
  LLM tool `build_firmware` documented and tested; pytest (mocked CLI)
  + vitest (panel states).
- **Depends-on:** T-116

---

## Long-tail platform (T-131)

### T-131 Fully-local / offline desktop — PGlite WASM-Postgres spike + Tauri (P3, demand-gated)
- **Tier:** B
- **Money/reach rationale:** A fully-local/offline desktop app
  (no server, no network, everything in-browser via WASM Postgres)
  is a potential unlock for air-gapped / offline / privacy-first
  personas. **Explicitly NOT a launch pillar** — ranked P3, demand-
  gated. The T-126 zero-dependency self-host path (BYO Postgres) is
  the correct near-term local story and is simpler, cheaper, and
  already covers the enterprise on-premise segment. This task begins
  only when there is validated demand signal for a no-server-process
  experience.
  **Rejected alternatives for the near-term local story:** embedded/
  auto-provisioned Postgres (unnecessary + maintenance liability);
  SQLite (forks SQL dialect forever); Electron bundling
  server+Postgres (hides infra, strictly worse than this spike).
- **Priority:** P3
- **Status:** 🔴 not started
- **Scope:** A time-boxed spike (one agent run): integrate
  `@electric-sql/pglite` (WASM Postgres) into a Vite browser build
  and verify that the Kerf schema migrations run cleanly against it;
  spike a minimal Tauri shell that wraps the Vite SPA. The spike
  deliverable is a documented feasibility report
  (`docs/plans/local-desktop-spike.md`) listing: migration
  compatibility, known schema / SQL dialect gaps, binary-size delta,
  and a recommended path forward (or a "not yet feasible" finding).
  No production code changes in this task.
- **Target files/packages:** `docs/plans/local-desktop-spike.md`
  (new, spike report), a throwaway `scripts/pglite_spike.mjs`
  (Vite + PGlite migration runner, not committed to main if the
  spike fails), `package.json` (add `@electric-sql/pglite` as a
  devDependency only, behind a feature flag).
- **Definition of Done:** spike report written and committed;
  report states clearly whether the Kerf baseline migration runs
  cleanly in PGlite; known incompatibilities (e.g. unsupported
  extensions, missing pg functions) are enumerated; Tauri shell
  feasibility assessed; a go/no-go recommendation is present.
- **Depends-on:** T-126

---

## Large-object storage — pointer / dedup / GC / threshold / hydration (T-132 … T-137)

These six refine the P1 git-as-substrate block (T-124 / T-125): the resolved
large-object decisions from the 2026-05-18 planning session. No Git LFS
server is run — the existing `files.content` (inline → git) vs
`files.storage_key` (blob → Tigris S3, sha256-addressed) seam IS the
large-file mechanism; these tasks formalize the pointer, the autodetect
predicate, the dedup ledger, and the billing / GC / hydration policies.
T-132 / T-133 / T-134 are independently landable now (no git-substrate
layer required); T-135 / T-136 / T-137 are design records.

### T-132 LFS-format blob pointer module + tests
- **Tier:** B
- **Money/reach rationale:** Adopting the documented 3-line Git-LFS
  pointer format (without running an LFS server) costs nothing, is
  universally understood by git tooling, and keeps a future real-LFS
  option trivial. Foundational to every large-object flow.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** A pure module that parses and serializes the Git-LFS
  pointer spec v1 exactly: `version https://git-lfs.github.com/spec/v1`,
  `oid sha256:<64-hex>`, `size <bytes>` (strict validation, byte-exact
  round-trip, typed errors). No I/O, no schema, no git layer.
- **Target files/packages:**
  `packages/kerf-core/src/kerf_core/storage/lfs_pointer.py` (new),
  `packages/kerf-core/tests/test_lfs_pointer.py` (new).
- **Definition of Done:** a valid pointer round-trips byte-exact;
  malformed pointers (bad oid length, non-sha256, missing/extra keys,
  non-integer size) raise a typed error; a fixture matches the
  canonical git-lfs byte layout; pytest green.
- **Depends-on:** none

### T-133 Large-file classifier + config threshold + tests
- **Tier:** A
- **Money/reach rationale:** The autodetect predicate decides what
  stays diff-able in git vs what becomes a Tigris blob — the load-
  bearing call for every project. The STEP-is-ASCII-but-huge case
  (size must dominate) prevents repo bloat across all sectors.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** A pure function `should_store_as_blob(name, size_bytes,
  sample: bytes, *, threshold) -> bool`: True if `size_bytes >
  threshold` (default 1 MiB) OR `sample` is not valid UTF-8.
  **Size dominates** — a 5 MB ASCII STEP file is a blob. One new
  setting `git_inline_max_bytes` (default 1048576) in
  `kerf_core/config.py`; this task is the SOLE editor of config.py
  among the storage tasks.
- **Target files/packages:**
  `packages/kerf-core/src/kerf_core/storage/classify.py` (new), one
  line in `packages/kerf-core/src/kerf_core/config.py`,
  `packages/kerf-core/tests/test_classify.py` (new).
- **Definition of Done:** small UTF-8 → inline; >1 MiB UTF-8 (STEP) →
  blob; small non-UTF-8 → blob; threshold honoured from config;
  exactly-threshold boundary tested; pytest green.
- **Depends-on:** none

### T-134 Blob object ledger schema — oid ref-count (sole migration owner)
- **Tier:** A
- **Money/reach rationale:** The ref-count ledger is the shared
  substrate under dedup billing (T-135) and GC (T-136). Exactly one
  task owns the migration so the clean-baseline rule isn't violated by
  parallel agents.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Clean-baseline DDL folded into the appropriate
  `00NN_*.sql` baseline CREATE TABLE (NO `alter table add column`
  shims): `blob_objects(oid text primary key, size_bytes bigint not
  null, first_workspace_id uuid references workspaces(id) on delete
  set null, created_at timestamptz not null default now())` and
  `blob_refs(oid text references blob_objects(oid) on delete cascade,
  project_id uuid references projects(id) on delete cascade, path
  text not null, created_at timestamptz not null default now(),
  primary key (oid, project_id, path))`. A small asyncpg query module
  (record_blob / add_ref / drop_ref / refcount / first_workspace).
  Reset local DB + re-run migrations + verify (documented reset
  workflow). The ONLY storage task touching migrations.
- **Target files/packages:** the appropriate
  `packages/kerf-core/src/kerf_core/db/migrations/00NN_*.sql` baseline
  (fold in; do not add a shim file),
  `packages/kerf-core/src/kerf_core/db/queries/blob_objects.py` (new),
  `packages/kerf-core/tests/test_blob_objects.py` (new).
- **Definition of Done:** fresh local schema reset applies all
  migrations with 0 back-stamped; record / add-ref / drop-ref /
  refcount behave; workspace/project delete cascades correctly;
  pytest green.
- **Depends-on:** none

### T-135 Dedup billing attribution — design record
- **Tier:** A
- **Money/reach rationale:** "Forks are free" is a core product
  promise; how shared-blob bytes are attributed is a real revenue /
  fairness decision, not an implementation detail.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Decision record for the agreed policy: the workspace that
  first uploads an oid (`blob_objects.first_workspace_id`) bears its
  `size_bytes`; any workspace/fork referencing an unchanged oid pays
  0; total billable storage for workspace W = Σ size_bytes where
  first_workspace_id = W, fed into the existing `$0.20/GB-month`,
  50 MB-free meter. Decide every edge case: first uploader deletes
  their only ref while others still reference; original project
  deleted; workspace transfer; interaction with `usage_events` /
  `cloud_user_balances`. No code.
- **Target files/packages:** `docs/plans/large-object-billing.md`
  (new). References the T-134 schema.
- **Definition of Done:** the doc states the rule unambiguously, gives
  the SQL shape of the periodic attribution query, gives a decided
  answer for every edge case, and names the exact meter integration
  point.
- **Depends-on:** T-134

### T-136 Large-object GC — design record
- **Tier:** B
- **Money/reach rationale:** Without GC, dedup storage grows forever;
  with wrong GC, a blob still reachable from a fork or old commit is
  deleted and data is lost. Needs a signed-off design before any
  sweep code exists.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Decision record: reclaim a Tigris object only when its
  oid has zero `blob_refs` AND is unreachable from any project's git
  history (a blob referenced by an old commit stays); a grace window
  before deletion; an idempotent sweep worker gated like the existing
  in-process workers (`KERF_INPROCESS_WORKERS`); safety invariants
  (never delete reachable; dry-run mode; metrics). No code.
- **Target files/packages:** `docs/plans/large-object-gc.md` (new).
  References the T-134 schema.
- **Definition of Done:** the doc defines the reachability predicate
  (refs + git history), the grace window, the sweep cadence / worker
  harness, and the safety invariants; explicitly states what is NOT
  collected.
- **Depends-on:** T-134

### T-137 Vanilla-clone hydration UX — design record
- **Tier:** B
- **Money/reach rationale:** "You can clone with plain git" is the
  anti-lock-in promise; the UX of "I cloned and got stubs, now what"
  must be documented and frictionless or the promise rings hollow.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Decision record: bare `git clone` yields LFS-format
  pointer stubs (T-132); the documented next step is `kerf hydrate` /
  `kerf pull-blobs` (resolves stubs → bytes from Tigris via the API);
  `kerf sync` hydrates implicitly; an optional opt-in git smudge/clean
  filter for transparent hydration; exact CLI surface, auth, and
  error messages for the cloned-but-not-hydrated state. No code.
- **Target files/packages:** `docs/plans/large-object-hydration.md`
  (new). References T-132 (pointer) and T-127 (`kerf sync`).
- **Definition of Done:** the doc specifies the CLI commands + flags,
  the stub→bytes resolution flow, the optional filter, and the exact
  user-facing messages for the not-yet-hydrated state.
- **Depends-on:** T-132

---

## CLI packaging + storage follow-ups + billing/migration cleanup (T-138 … T-141)

Surfaced 2026-05-18 while landing T-124..T-137. T-141 is P0 (money/schema
correctness — real bugs found by the test wave); the rest are P1.

### T-138 — (reserved / skipped)
Intentionally unused to keep T-139+ stable.

### T-139 kerf-cli packaging integration into the monorepo
- **Tier:** B
- **Money/reach rationale:** the install story (`pip install kerf` /
  `pipx install kerf` / `pip install 'kerf[server]'`) is the front door
  for every self-host + cloud-client user; it must actually work from a
  clean machine, not just as a workspace stub.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** make `packages/kerf-cli` a first-class workspace member:
  verify the `kerf` console entry installs onto PATH from a clean
  `pip install kerf`; the `[server]` extra pulls every required
  `kerf-*` runtime package (kerf-core/api/auth/billing/cloud) with
  correct version pins; root `pyproject.toml` workspace + build wiring;
  a clean-venv smoke (`pip install -e`, `kerf --help`, `kerf serve`
  fail-fast). Canonical docs command is `pipx install kerf`.
- **Target files/packages:** `packages/kerf-cli/pyproject.toml`, root
  `pyproject.toml`, a clean-install smoke test.
- **Definition of Done:** fresh venv `pip install` (thin) and
  `pip install '.[server]'` both yield a working `kerf` on PATH;
  `kerf serve` fail-fast verified; smoke test green.
- **Depends-on:** T-126

### T-140 project-scoped blob-serve endpoint (`kerf hydrate` backend)
- **Tier:** A
- **Money/reach rationale:** `kerf hydrate` (T-137) is built but 404s —
  the documented `GET /api/projects/{id}/blobs/{oid}` route does not
  exist server-side, so the anti-lock-in hydrate flow is non-functional
  end-to-end until this lands.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** add an authed, ownership-checked `GET
  /api/projects/{pid}/blobs/{oid}` to kerf-api that streams the
  content-addressed object (via `blob_storage_key`) for an oid the
  project actually references (`blob_refs`); 404 otherwise. Mirror the
  existing cover/workshop-media visibility rules.
- **Target files/packages:** `packages/kerf-api/src/kerf_api/routes.py`
  + a test.
- **Definition of Done:** referenced oid → 200 + correct bytes;
  unreferenced/cross-project oid → 404; unauth → 401; `kerf hydrate`
  resolves against it; pytest green.
- **Depends-on:** T-125, T-134, T-137

### T-141 billing/migration correctness cleanup (coordinated, sole owner)
- **Tier:** A
- **Money/reach rationale:** three real production bugs + a clean-
  baseline violation found by the T-117/T-118/T-125/T-136 wave. Money
  correctness — must be fixed as one coordinated pass with exclusive DB
  access (requires a schema reset) before further storage work.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** (a) `kerf_billing/spend.py` `_commit_paid`
  `VALUES ($1, -$2)` → `-$2::numeric` (KerfPaid debit currently raises
  AmbiguousFunctionError and never executes) + flip the 2
  `xfail(strict)` tests in `test_quota.py` to real asserts; (b) fold
  T-136's `last_unref_at` into `0011_blob_ledger.sql`'s `blob_objects`
  CREATE TABLE, DELETE the `0012_blob_gc_last_unref_at.sql`
  add-column shim, then integrate T-136's GC module/queries/plugin/
  tests (from commit `9dfff29`, minus the shim); (c)
  `cloud_user_balances.credits_usd` `numeric(12,4)` → `numeric(12,6)`
  in the 0008 baseline so storage debits stop truncating; (d) add the
  missing `cloud_git_repos`/`cloud_git_commits`/`cloud_git_branches`
  clean-baseline migration (T-125's handler depends on them; they have
  no migration in-tree). After edits: DROP SCHEMA + re-run runner →
  assert all migrations applied, 0 back-stamped; run the full
  billing/storage suites green.
- **Target files/packages:** `packages/kerf-billing/src/kerf_billing/spend.py`,
  `packages/kerf-billing/tests/test_quota.py`,
  `packages/kerf-core/.../migrations/0008_billing.sql` + `0011_blob_ledger.sql`
  (+ delete `0012_*`), a new `cloud_git` baseline migration,
  `kerf_core/db/queries/blob_objects.py`, `kerf_billing/blob_gc.py`
  + registration + tests (from 9dfff29).
- **Definition of Done:** fresh schema reset → all migrations, 0 back-
  stamped; `test_quota.py` fully green (no xfail); storage debit keeps
  6dp; `cloud_git_*` tables present; T-136 GC tests green; no
  `alter table add column` shim remains.
- **Depends-on:** T-117, T-118, T-125, T-136 (work product 9dfff29)

### T-142 Git panel does not react to collapse like the chat panel
- **Tier:** B
- **Money/reach rationale:** user-reported UX bug (2026-05-18, flagged
  **priority**). The Git side panel ignores the collapse/expand
  interaction that the Chat panel handles correctly — inconsistent,
  feels broken, hurts the core editor experience every git user hits.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** find how the Chat panel implements collapse/expand (the
  correct reference — state, animation, width persistence, the
  panel/layout store) and apply the same behavior to the Git panel so
  collapsing/expanding it is identical to Chat. Frontend only (`src/`).
- **Target files/packages:** `src/` editor panel/layout components
  (the Git view + Chat view + shared panel/collapse state).
- **Definition of Done:** collapsing/expanding the Git panel behaves
  identically to Chat (toggle, animation, persisted width); vitest on
  the shared logic where testable. NOTE: cannot be browser-tested by an
  agent — needs user verification on dev (one change, then confirm),
  per the UI-polish loop convention.
- **Depends-on:** none

### T-143 Show app version number in the frontend (Settings)
- **Tier:** B
- **Money/reach rationale:** user-flagged **priority** (2026-05-18).
  A visible version number is table-stakes for support/bug-reports
  ("what version are you on") and trust — cheap, high-signal.
- **Priority:** P0
- **Status:** ✅ shipped (integrated this session)
- **Scope:** surface the build-time version in the UI — preferably on
  the Settings page (and/or a subtle app footer). The value is ALREADY
  wired: `vite.config.js` defines `__APP_VERSION__` from
  `package.json`'s `version`. Just consume that global and render it;
  no build-pipeline change needed. Frontend only (`src/`).
- **Target files/packages:** `src/` — the Settings route/component
  (+ optionally shared footer/chrome); reference `__APP_VERSION__`.
- **Definition of Done:** the running app shows its version (matching
  `package.json`) in Settings; vitest on any extracted helper where
  testable; build clean. NOTE: UI change — needs user dev verification
  per the UI-polish loop convention.
- **Depends-on:** none

---

## Git UX + multi-provider sync (T-144 … T-149)

Surfaced 2026-05-18. **Architecture (reaffirmed):** Kerf's hosted git is
ALWAYS the system of record; GitHub/GitLab are an *optional additional
sync/mirror*, each env-gated (GitHub app keys exist now; wire GitLab too —
gracefully disabled until its keys are set). Goal: a git-graph panel + a
git settings UI to pick the provider, robust + tested. Dependency-ordered;
frontend tasks (T-147/T-148) serialize behind other frontend work.

### T-144 Git external-sync provider abstraction
- **Tier:** A
- **Money/reach rationale:** the seam everything else hangs off; lets a
  second provider plug in without forking the sync path. Keeps "our git
  is SoR; external = optional mirror" explicit.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** extract the existing GitHub-app push/pull into a
  `GitSyncProvider` interface (`name`, `is_configured(settings)`,
  `connect/disconnect`, `push(repo)`, `pull(repo)`, `status`). Implement
  `GitHubProvider` = current behaviour. Availability is env-gated
  (GitHub app settings present → available). Our cloud git commit/fork
  path (T-125) is untouched — provider is additive mirror only.
- **Target files/packages:** `packages/kerf-cloud/` — `github_app.py`
  + a new `git_providers/` module + routes glue. No migration.
- **Definition of Done:** GitHub sync behaves exactly as before but
  through the provider interface; `is_configured` false → provider
  absent, no errors; unit tests for the interface + GitHub provider.
- **Depends-on:** T-125

### T-145 GitLab provider implementation
- **Tier:** A
- **Money/reach rationale:** doubles the addressable "sync to my forge"
  audience; GitLab is the dominant self-hosted forge in enterprise.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** `GitLabProvider` (OAuth app or PAT; push/pull mirror) +
  `cloud_gitlab_*` settings. Keys absent now → provider reports
  unconfigured and is hidden; code path still exercised by tests with
  injected fakes. If a token table is needed, fold it CLEAN-BASELINE
  into the appropriate migration (sole-migration-owner; coordinate —
  do not add an alter shim).
- **Target files/packages:** `packages/kerf-cloud/git_providers/gitlab.py`
  + settings; migration only if required (clean baseline).
- **Definition of Done:** GitLab provider push/pull works against a
  faked GitLab API; unconfigured → cleanly disabled; tests green;
  migration (if any) resets clean, 0 back-stamped.
- **Depends-on:** T-144

### T-146 Git provider settings API
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** endpoints to list env-available providers, connect/
  disconnect a project's external mirror, and report sync status —
  copy must make clear Kerf git is always retained; this only toggles
  an additional mirror. Gated: never expose a provider whose app isn't
  configured.
- **Target files/packages:** `packages/kerf-cloud/` routes + tests.
- **Definition of Done:** API lists only configured providers;
  connect/disconnect/status work; unauth + cross-tenant rejected;
  tests green.
- **Depends-on:** T-144

### T-147 Frontend — Git Settings UI (choose provider)
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** a Git settings surface (in the Git panel) to pick/connect
  GitHub or GitLab — only providers the backend reports as configured
  are shown; clear "our git is always kept" framing; show sync status.
  Frontend only.
- **Target files/packages:** `src/cloud/` git settings component +
  wiring.
- **Definition of Done:** only configured providers offered; connect/
  status reflected; vitest on logic; build clean. UI change — needs
  user dev verification.
- **Depends-on:** T-146, T-148

### T-148 Frontend — Git panel as a git graph
- **Tier:** A
- **Money/reach rationale:** the headline UX ask — a real commit-graph
  view (branches/commits DAG) instead of the minimal panel; makes the
  cloud-git substrate legible and trustworthy.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** render a commit graph in the Git panel from the cloud-git
  data (`cloud_git_commits`/`cloud_git_branches`, landed via T-125/
  T-141) — branch lanes, commit nodes, messages, HEAD. Builds on the
  T-142 inline-panel layout. Frontend only.
- **Target files/packages:** `src/cloud/GitPanel.jsx` + a new graph
  component + the git data hook; a server list endpoint only if one is
  missing (document, don't overreach).
- **Definition of Done:** panel shows a correct commit/branch graph
  for a project with history; empty-repo safe; vitest on the graph
  layout logic; build clean. UI change — needs user dev verification.
- **Depends-on:** T-142

### T-149 Robust multi-provider sync — E2E + hardening
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** end-to-end coverage: Kerf git is SoR; pushing/pulling an
  optional GitHub *and* GitLab mirror; env-gating; auth failure,
  network error, partial-sync, and re-sync idempotency are robust and
  surfaced. Simulated providers (no live tokens needed).
- **Target files/packages:** `packages/kerf-cloud/tests/` + any
  hardening in the provider modules.
- **Definition of Done:** both providers’ happy + failure paths tested
  with fakes; our-git-untouched invariant asserted; suite green.
- **Depends-on:** T-144, T-145, T-146

### T-150 GitReachabilityOracle — let blob GC leave dry-run
- **Tier:** B
- **Money/reach rationale:** the only remaining storage loose-end.
  T-136's GC worker ships dry-run-safe behind a `GitReachabilityOracle`
  interface; until a real oracle is registered no unreferenced blob is
  ever reclaimed → dedup storage grows unbounded. Closing this makes the
  storage substrate fully self-maintaining.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** implement a `GitReachabilityOracle` that, given an oid,
  reports whether ANY commit reachable from ANY ref of the project's
  bare repo contains an LFS pointer for it (must include history, not
  just HEAD). Register it so `BlobGCWorker` uses it; keep the dry-run
  default and require an explicit opt-in env flag to actually delete.
- **Target files/packages:** `packages/kerf-billing/blob_gc.py` (wire
  the oracle), a new oracle impl reading the bare repos (kerf-core
  storage / pygit2), + tests.
- **Definition of Done:** oracle correctly classifies reachable vs
  unreachable against real repos incl. history; GC reclaims ONLY
  unreferenced + unreachable + past-grace oids; still inert unless the
  opt-in flag is set; tests green.
- **Depends-on:** T-125, T-136

### T-151 cloud_git_commits parent tracking → real merge graph
- **Tier:** B
- **Money/reach rationale:** T-148's commit-graph renders as a linear
  chain because `cloud_git_commits` stores no parent relationships and
  `/projects/{pid}/git/log` returns no `parent_shas`; merge lanes only
  appear once parents are recorded. Small, completes the git-graph UX.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** add parent tracking to `cloud_git_commits` (clean-baseline:
  a `parent_shas text[]` column folded into `0012_cloud_git.sql`, NOT
  an alter shim); record real parents in the materialize/commit handler
  (pygit2 commit parents); expose `parent_shas` in the `/git/log`
  response. **SOLO migration task** — requires a DROP SCHEMA reset, so
  run it when NO other agent is using the shared DB; verify all
  migrations apply, 0 back-stamped.
- **Target files/packages:** `0012_cloud_git.sql`,
  `packages/kerf-cloud/src/kerf_cloud/routes.py` (commit handler +
  /git/log), tests. T-148's `gitGraph.js` already consumes `parent_shas`.
- **Definition of Done:** commits store parents; `/git/log` returns
  `parent_shas`; a merge commit renders with a merge lane; schema reset
  clean, 0 back-stamped; tests green.
- **Depends-on:** T-125, T-148

### T-152 GitLab connection persistence (clean-baseline migration)
- **Tier:** B
- **Money/reach rationale:** T-145's `GitLabProvider` works for push/
  pull/status but `connect`/`disconnect` cannot persist — the schema
  has no GitLab columns/token table. Until this lands, a GitLab mirror
  can't be durably attached to a project.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** clean-baseline DDL — add `gitlab_host`/`gitlab_namespace`/
  `gitlab_project` to `cloud_git_repos` (folded into `0012_cloud_git.sql`,
  NOT an alter shim) and a `cloud_gitlab_tokens` table analogous to
  `cloud_github_tokens` (fold into its baseline `0006`/`0010`). Wire
  `GitLabProvider.connect`/`disconnect`/`status` to persist. **SOLO
  migration task** — DROP SCHEMA reset; run only when NO other agent
  uses the shared DB; verify all migrations apply, 0 back-stamped.
- **Target files/packages:** `0012_cloud_git.sql` + the github-tokens
  baseline, `git_providers/gitlab.py`, tests.
- **Definition of Done:** GitLab connect/disconnect persist + survive
  reload; schema reset clean, 0 back-stamped; existing git-provider
  tests still green.
- **Depends-on:** T-145

### T-153 occtWorker tube-sweep for 3D wiring harness (T-36 follow-up)
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** consume `kerf_wiring.harness3d.HarnessSegment` (waypoints +
  bundle_diameter_mm) in `src/lib/occtWorker.js` to render the harness as
  an OCCT tube-sweep along the polyline. Frontend/JS — deferred from T-36
  (out of that task's wiring-package scope).
- **Target files/packages:** `src/lib/occtWorker.js` + a vitest.
- **Definition of Done:** a HarnessSegment renders as a swept tube of the
  correct diameter along its waypoints; vitest on the layout math; build
  clean. UI/geometry change — needs user dev verification.
- **Depends-on:** T-36

### T-154 Coordinated DB reset — activate accumulated baseline edits
- **Tier:** A
- **Priority:** P0
- **Status:** 🔴 not started
- **Scope:** parent-owned, SOLO (run only when NO agent uses the shared
  DB). Several baseline migration edits are committed but not applied to
  the live local DB (idempotent-by-filename): T-130 added `'firmware'`
  to `0001` `files_kind_check`; collect any other flagged baseline edits
  from in-flight agents. DROP SCHEMA + recreate + re-run runner → assert
  ALL migrations applied, 0 back-stamped; verify the new file-kind(s) +
  any added objects exist; run the affected suites green. Recurring
  loop maintenance task — re-open whenever new flagged baseline edits
  accumulate.
- **Depends-on:** (whenever DB is free of agents)

### T-155 Nesting layout view (T-53 follow-up, frontend)
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** SVG/canvas layout view rendering the T-53 nest result
  (sheet + placed parts + utilization). Frontend; deferred from T-53
  (out of that task's Python-package scope).
- **Target files/packages:** `src/` nesting layout component + vitest.
- **Definition of Done:** a nest result renders parts within sheet
  bounds with utilization label; vitest on layout math; build clean.
  UI change — needs user dev verification.
- **Depends-on:** T-53

