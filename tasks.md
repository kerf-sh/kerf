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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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

### T-100 FEM matching CalculiX / Z88 / Mystran depth (epic — split into T-100a..h)
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive simulation depth
  (2 personas). Seed modules (`nonlinear`, `explicit`, `acoustics_fem`,
  `em_field`, `em_highfreq`, `fatigue_fem`) are already in
  `packages/kerf-fem/`; needs wiring through the public `analysis_type`
  enum + reference-tool match. FEM-hardening stream is in flight in
  parallel; this task captures **what's left after that lands**.
- **Priority:** P2
- **Status:** 🚧 umbrella — split into bounded sub-tasks **T-100a..h**.
  Reference-value suite landed (2026-05-17): `kerf_fem.pressure_load` +
  43-test `test_fem_refvalues.py` with Roark / Blevins / Incropera
  oracles, 42 green, one ASTM E1049 rainflow test skipped (real bug
  flagged in `fatigue_fem._rainflow`). Public `analysis_type` enum-wiring
  + CalculiX / Z88 / Mystran reference-tool match decomposed below.
- **Scope:** Wire the seed nonlinear / explicit / acoustics / EM /
  fatigue modules through the public analysis enum + LLM tool surface,
  then match a CalculiX (nonlinear / contact) + Z88 (linear / modal /
  nonlinear) + Mystran (modal / aeroelastic) reference test corpus.
  CalculiX / Z88 / Mystran are invoked as subprocesses with graceful
  degrade when the binary is absent (same pattern as CuraEngine).
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/` (`tools.py`
  analysis-enum extension, plugin capability advertisements,
  `nonlinear.py` / `explicit.py` / `acoustics_fem.py` / `em_field.py` /
  `em_highfreq.py` / `fatigue_fem.py`, `pressure_load.py`), reference-
  test corpus under `packages/kerf-fem/tests/`.
- **Definition of Done:** rolled up from T-100a..h.
- **Depends-on:** none

### T-101 CFD CfdOF-class — turbulence + 3-D meshing + OpenFOAM bridge (epic — split into T-101a..f)
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive + aerospace
  simulation depth (3 personas, P2 — moat depth not P0 unlock). Potential
  flow (`cfd_potential.py`) is the seed already in flight; full CfdOF
  parity is engine-class.
- **Priority:** P2
- **Status:** 🚧 umbrella — split into bounded sub-tasks **T-101a..f**.
  2-D laminar foundation landed (2026-05-17): `kerf_fem.cfd_potential`
  (potential flow, `Cp(θ)=1−4sin²θ` analytic oracle) +
  `kerf_fem.cfd_navier_stokes` (lid-driven cavity, Ghia Re=100 reference);
  61 hermetic CFD tests in `test_cfd.py`. Turbulence models, 3-D meshing,
  and OpenFOAM bridge decomposed below.
- **Scope:** Extend past the 2-D laminar foundation into full
  Navier-Stokes + heat transfer with turbulence models (k-ε / k-ω SST),
  3-D unstructured meshing, and an OpenFOAM bridge (graceful degrade when
  the binary is absent — same pattern as CuraEngine). OpenFOAM is invoked
  as a subprocess; the solver is unmodified.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_*.py`,
  `packages/kerf-fem/src/kerf_fem/openfoam_bridge.py`, tests (`test_cfd.py`
  is the seed).
- **Definition of Done:** rolled up from T-101a..f.
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

### T-104 Kernel G3 + NURBS Phase 4 trim-by-curve + class-A leading (epic — split into T-104a..h)
- **Tier:** A
- **Money/reach rationale:** Automotive + jewelry Class-A surfacing
  depth (2 personas). G3 curvature combs partially shipped (#100);
  imprint (GK-19) + class-A leading still to go. Kernel-side depth →
  opus-spine; cross-sector reach via the surfacing path.
- **Priority:** P1
- **Status:** 🚧 umbrella — split into bounded sub-tasks **T-104a..h**
  (same shape as T-106a..f). Decomposition rationale, current kernel
  state, dependency graph + the structural-impossibility call-outs in
  `docs/plans/occt-phase4.md`. **Honest scope line:** algorithmic G3 is
  *impossible on stock OCCT* (`GeomAbs_G3` absent from the
  `GeomAbs_Shape` enum) — the OCCT answer is the already-shipped
  *visualization-only* curvature-comb path; the genuinely-new G3 here is
  **pure-Python NURBS** (T-104a/b/c, roadmap GK-62, not OCCT-gated).
  General NURBS×NURBS trim stays delegated to the OCCT worker; T-104's
  pure-Python trim is bounded to the plane/cyl/sphere carrier matrix.
- **Scope:** Extend the Phase-4 NURBS surfacing path past the shipped
  C0–C2 / G0–G2 + curvature combs into algorithmic G3 (custom-WASM
  required — stock OCCT cannot enforce `GeomAbs_G3`), full trim-by-curve
  / imprint (GK-19 in the geometry-kernel roadmap), and the class-A
  leading surface-quality workflow.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/` (G3 helpers, trim-by-curve, leading), tests; aligns with
  `docs/plans/geometry-kernel-roadmap.md` GK-NN slots.
- **Definition of Done:** rolled up from T-104a..h.
- **Depends-on:** none

### T-104a G3 (curvature-rate) continuity residual oracle — pure-Python
- **Tier:** A
- **Money/reach rationale:** Foundation for the entire algorithmic-G3
  spine and the class-A acceptance gate (automotive + jewelry Class-A,
  2 personas). The single highest-leverage gate in the epic — every
  later G3/class-A sub-task asserts against this oracle.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Add a pure-Python **G3 residual** to the existing
  continuity machinery (sibling to
  `surface_fillet.curvature_comb_continuity_residual`, which today
  tops out at G1/G2). Compute the cross-boundary **curvature-rate**
  (third-derivative / dκ/ds) at sampled seam points using the analytic
  rational derivatives already landed in `nurbs.py` (GK-02) — NOT
  finite differences. This is pure NURBS math: the stock-OCCT
  `GeomAbs_G3` impossibility does **not** apply to the pure-Python
  layer (see `docs/plans/occt-phase4.md` §3). Also export a numeric
  curvature comb-of-combs (GK-65) value so the gate and tests share
  one definition. No OCCT, no worker, no UI.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/surface_fillet.py` (extend the residual fn; additive only),
  `geom/blend_srf.py` (re-export), `packages/kerf-cad-core/tests/`.
- **Definition of Done:** for two surfaces analytically known to meet
  G3 at a seam, the residual is `< 1e-5`; for a deliberately G2-only
  (curvature-rate-discontinuous) join the residual is reported large;
  comb-of-combs magnitude on a circle/cylinder = analytic dκ/ds to
  `1e-9`; pytest with closed-form oracles only; ties roadmap GK-62
  (oracle half) + GK-65.
- **Depends-on:** none

### T-104b Pure-Python G3 blend strip — rebuild blend_srf G2/G3 path
- **Tier:** A
- **Money/reach rationale:** The headline *new kernel capability* of
  the epic — a real curvature-continuous→curvature-rate-continuous
  NURBS blend (Class-A surfacing for automotive + jewelry). Today
  `blend_srf.g2_blend_point` is a fake additive nudge; this delivers
  the genuine pure-Python G3 the OCCT path structurally cannot.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Rebuild the blend-strip constructor so it can enforce
  **G3** between two NURBS surfaces along a shared-edge descriptor
  (extend the verified `surface_fillet.surface_blend_g1_g2` pattern to
  a higher-degree-in-v strip with enough inner control rows to satisfy
  position + tangent + curvature + curvature-rate at both seams).
  Delete / quarantine the bogus `blend_srf.g2_blend_point` additive
  nudge. Pure-Python NURBS only — no OCCT, no worker. Validate every
  result against the T-104a residual oracle.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/blend_srf.py` (rebuild G2/G3 path),
  `geom/surface_fillet.py` (shared helpers; additive),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** a G3 blend between two known surfaces passes
  the T-104a residual (`< 1e-5`) at every sampled seam point; G1/G2
  residuals also satisfied; boundary interpolation exact to `1e-9`;
  pytest analytic oracles; ties roadmap GK-62 (blend half).
- **Depends-on:** T-104a

### T-104c G3 blend trims + sews supports to a Body (bounded matrix)
- **Tier:** A
- **Money/reach rationale:** Makes the G3 blend a *usable solid* rather
  than a bare surface — the deliverable a jewelry/automotive user
  actually consumes (filleted/blended Class-A body, not a loose patch).
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Trim the two support surfaces back to the G3 blend's seam
  curves and sew blend+supports into a `validate_body`-clean `Body`,
  following the **already-landed** GK-26 (`fillet_solid.py`) +
  `sew.py` + `boolean.py` imprint pattern. Bounded — restrict support
  inputs to the **plane / world-axis cylinder / sphere** carrier
  matrix `boolean.py` already supports (docstring lines 9-44); raise
  `unsupported-input` for arbitrary NURBS×NURBS (that stays on the
  OCCT worker; see `docs/plans/occt-phase4.md` §6). Pure-Python only.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/blend_srf.py` (body-emitting entrypoint),
  `geom/sew.py` / `geom/fillet_solid.py` (reuse, additive),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** G3 blend across a planar-pair / planar-cyl
  edge → `validate_body` ok and 2-manifold; volume matches the
  closed-form expectation to `1e-6`; non-matrix input returns a
  structured `unsupported-input`, never an invalid `Body`; pytest.
- **Depends-on:** T-104b

### T-104d Pure-Python trim-by-curve (GK-40) — analytic carrier matrix
- **Tier:** A
- **Money/reach rationale:** Closes the GK-40 long-tail and removes a
  hard OCCT coupling for the bounded matrix — directly serves the
  jewelry "cut a stone-setting window into a shank" and automotive
  panel-trim workflows; testable in-process (no WASM).
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Pure-Python **trim face by a projected / SSI curve**:
  given a `Face` whose surface is in the analytic carrier matrix
  (plane / world-axis cylinder / sphere) and a 3D cutter curve, build
  the seam via the **already-landed** SSI (GK-09) + closest-point
  pullback (GK-07), imprint it into the face's loop set generalising
  the GK-19 `boolean.py` `mef`/`kemr` split, and keep the requested
  side — emitting a `validate_body`-clean trimmed `Face`/`Body`. This
  replaces the FD-projection-only `trim_curve.trim_face` *for the
  matrix*; arbitrary NURBS×NURBS explicitly stays delegated to the
  OCCT worker (`feature_trim_by_curve`) and is out of scope (see
  `docs/plans/occt-phase4.md` §3.3/§6). Pure-Python; no worker; no UI.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/trim_curve.py` (pure-Py split path; keep existing API),
  `geom/boolean.py` (reuse imprint helpers; additive),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** trimming a plane by a cylinder yields the
  exact circular boundary loop to `1e-7` and a `validate_body`-clean
  trimmed face; keep-side selects the correct region; non-matrix
  carrier returns a structured `unsupported-input` (not an exception,
  not an invalid body); pytest analytic oracles; ties roadmap GK-40.
- **Depends-on:** T-104c

### T-104e Trim side-selection + validation contract; in-proc wiring
- **Tier:** A
- **Money/reach rationale:** Makes T-104d's pure-Python trim the
  *default in-process answer* for the bounded matrix (instant, no
  WASM round-trip), with the OCCT worker correctly retained as the
  fallback for everything else — the testability + decoupling win.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Harden the **side-selection heuristic** (area / point-in-
  region, mirroring `boolean.py` region classification) and the
  validation contract that the existing `surfacing.feature_trim_by_
  curve` worker path already documents (`keep_side`
  positive/negative). Wire the T-104d pure-Python result as the
  in-process answer **when the carrier is in the analytic matrix**;
  fall through to the existing OCCT-worker path otherwise (invert
  today's "worker is the only path" only for the matrix). Add the
  `geom/__init__.py` façade export + docstring the pure-Py vs OCCT
  split (GK-71-style). Do **not** touch JS/WASM worker code or the
  C2-T12 Section+prism fallback (out of scope, owned elsewhere).
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/trim_curve.py`, `geom/__init__.py` (façade export),
  `packages/kerf-cad-core/src/kerf_cad_core/surfacing.py` (in-proc
  dispatch guard only — no worker/JS edits),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** a matrix-carrier trim resolves in-process
  with the correct side and no worker call; a non-matrix carrier still
  routes to the OCCT worker unchanged; existing trim tests still pass;
  import-surface snapshot test green; pytest.
- **Depends-on:** T-104c, T-104d

### T-104f Zebra / reflection-line continuity analyser (GK-38)
- **Tier:** A
- **Money/reach rationale:** Zebra is *the* Class-A inspection idiom
  (Alias/ICEM/Rhino). Cross-sector reach: automotive A-surface review
  + jewelry highlight inspection (2 personas). Parallelisable with
  the trim spine.
- **Priority:** P1
- **Status:** ✅ shipped (integrated this session)
- **Scope:** Promote the single-point `surface_analysis.zebra_stripe`
  scalar into a **continuity analyser**: sample reflection-line /
  zebra stripes across a shared edge between two surfaces and detect
  stripe-tangent discontinuity (G1 break) and stripe-curvature
  discontinuity (G2 break), reusing the analytic partials from GK-02.
  Numeric output only (the rendered overlay is shipped elsewhere as
  the worker `surface_curvature_combs` viz path — do not touch UI/
  worker). Pure-Python; analytic oracle.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/surface_analysis.py` (additive analyser fn),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** zebra stripes report continuous across a
  constructed G1 join and a detected tangent-discontinuity across a
  G0 join; result is deterministic and analytically oracled (no
  "looks plausible"); pytest; ties roadmap GK-38.
- **Depends-on:** T-104a

### T-104g Class-A acceptance harness — combs + zebra + G0..G3 gate
- **Tier:** A
- **Money/reach rationale:** The acceptance gate a Class-A shop runs
  before sign-off — turns the kernel depth into a checkable deliverable
  for both target personas. Consumes the T-104a residual + T-104f
  analyser.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** A pure-Python class-A acceptance harness that runs
  curvature combs + the T-104f zebra analyser + a **G0/G1/G2/G3**
  continuity report (extend `surface_analysis.edge_continuity_report`,
  which today stops at G2, with the T-104a G3 residual column) on a
  reference A-surface fixture, and returns a structured pass/fail per
  gate. A deliberately G0 (or G2-only) variant of the fixture must
  fail the corresponding gate. Pure-Python; analytic; no UI/worker.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/surface_analysis.py` (G3 column + harness; additive),
  `packages/kerf-cad-core/tests/` (reference + degraded fixtures).
- **Definition of Done:** the good A-surface fixture passes all gates;
  the G0 variant fails the G1 gate and the G2-only variant fails the
  G3 gate, each with the documented numeric residual; pytest closed-
  form oracles; ties roadmap GK-64.
- **Depends-on:** T-104a, T-104f

### T-104h Class-A *leading* workflow — hot-spot flagging surface
- **Tier:** A
- **Money/reach rationale:** The user-facing payoff of the whole epic:
  "flag the hot-spots on my fender / bezel." The product-layer cap on
  the Class-A kernel depth; closes the original T-104 "class-A leading
  workflow flags hot-spots" DoD.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** A pure-Python *leading* pass that consumes the T-104g
  harness output and produces a structured **hot-spot map** over a
  surface: per-(u,v) classification of curvature-rate spikes /
  reflection-line kinks / G-continuity violations, ranked, with the
  worst regions flagged for the surfacing operator. Output is a
  serialisable diagnostic object (the rendered overlay is the already-
  shipped worker comb path — do not touch UI/worker). Pure-Python;
  deterministic; analytic oracle on a synthetic surface with a known
  injected defect.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/
  geom/surface_analysis.py` (leading pass; additive),
  `packages/kerf-cad-core/tests/`.
- **Definition of Done:** on a synthetic Class-A test surface with a
  deliberately injected curvature-rate hot-spot, the leading pass
  flags exactly that region as the worst and a clean surface produces
  an empty hot-spot set; deterministic; pytest analytic oracle;
  closes the original T-104 leading-workflow DoD.
- **Depends-on:** T-104g

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
- **Status:** ✅ shipped (epic umbrella — all children T-106a..f ✅ this session)
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
- **Status:** ✅ shipped this session (T-106d/render tables in 0010 await T-154 reset; UI needs dev verify)
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
- **Status:** ✅ shipped this session (T-106d/render tables in 0010 await T-154 reset; UI needs dev verify)
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
- **Status:** ✅ shipped this session (T-106d/render tables in 0010 await T-154 reset; UI needs dev verify)
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
- **Status:** ✅ shipped this session (T-106d/render tables in 0010 await T-154 reset; UI needs dev verify)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped (integrated this session)
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
- **Status:** ✅ shipped this session (needs user dev verification — Web Worker geometry)
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
- **Status:** ✅ done — coordinated reset applied; 12 migrations 0 back-stamped; objects verified
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
- **Status:** ✅ shipped this session (component; needs dev verify + FileTree `nest`-kind wiring follow-on)
- **Scope:** SVG/canvas layout view rendering the T-53 nest result
  (sheet + placed parts + utilization). Frontend; deferred from T-53
  (out of that task's Python-package scope).
- **Target files/packages:** `src/` nesting layout component + vitest.
- **Definition of Done:** a nest result renders parts within sheet
  bounds with utilization label; vitest on layout math; build clean.
  UI change — needs user dev verification.
- **Depends-on:** T-53

---

## FEM epic sub-tasks (T-100a … T-100h)

Decomposition of the T-100 umbrella. Each sub-task is a single isolated-worktree
Sonnet run. CalculiX / Z88 / Mystran are subprocess-invoked and unmodified;
graceful degrade when the binary is absent (same pattern as CuraEngine).

### T-100a Fix `fatigue_fem._rainflow` ASTM E1049 bug (skipped test)
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive fatigue analysis (2 personas). The ASTM E1049 rainflow test is the only failing case in the 43-test reference-value suite; it must be green before fatigue_fem ships as a public analysis type.
- **Priority:** P2
- **Status:** ✅ shipped (already landed pre-session 5f84916; marker reconciled)
- **Scope:** Diagnose and fix the `fatigue_fem._rainflow` implementation so it matches the ASTM E1049 4-point rainflow-counting algorithm. Re-enable the previously skipped test in `test_fem_refvalues.py`. Pure Python; no external solver needed. One function, one test.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/fatigue_fem.py` (`_rainflow`), `packages/kerf-fem/tests/test_fem_refvalues.py` (unskip the ASTM E1049 case).
- **Definition of Done:** the previously skipped test passes; the fix matches the ASTM E1049 counting table (cycles, ranges, means) to the documented tolerance; no other tests regressed; pytest green.
- **Depends-on:** none

### T-100b Wire `nonlinear` + `explicit` through the public analysis enum
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive nonlinear / crash analysis. The seed modules exist; they are invisible to the LLM tool surface until wired through `tools.py`.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `packages/kerf-fem/src/kerf_fem/tools.py` `analysis_type` enum to accept `nonlinear` and `explicit`. Route each type to the corresponding seed module (`nonlinear.py`, `explicit.py`). Publish capability tags in `GET /health/capabilities`. Add analytic reference tests: nonlinear cantilever yielding (compare elastic-plastic tip deflection to analytical J2 plasticity solution); explicit impact pulse (kinetic-energy conservation to 1%). Binary-absent → graceful sentinel.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/tools.py`, `nonlinear.py`, `explicit.py`, `packages/kerf-fem/tests/test_fem_refvalues.py` (extend).
- **Definition of Done:** `run_fem(analysis_type='nonlinear', ...)` and `run_fem(analysis_type='explicit', ...)` execute when the solver binary is present; graceful sentinel when absent; capability tags in `/health/capabilities`; reference tests green; pytest.
- **Depends-on:** T-100a

### T-100c Wire `acoustics_fem` + `em_field` + `em_highfreq` through the enum
- **Tier:** A
- **Money/reach rationale:** Mechanical + electronics simulation depth (vibro-acoustics, EM shielding, RF PCB — 2+ personas). Three seed modules wired in one task (they share the same enum-extension pattern as T-100b).
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `tools.py` enum for `acoustics_fem`, `em_field`, `em_highfreq`. Route to seed modules. Publish capability tags. Reference tests: `acoustics_fem` — room-mode frequency for a rectangular cavity vs analytic formula; `em_field` — E-field in a parallel-plate capacitor vs V/d; `em_highfreq` — resonant frequency of a rectangular waveguide TE10 mode vs analytic formula. Each: binary-absent → sentinel.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/tools.py`, `acoustics_fem.py`, `em_field.py`, `em_highfreq.py`, `packages/kerf-fem/tests/test_fem_refvalues.py` (extend).
- **Definition of Done:** all three analysis types run with binary present, sentinel with absent; capability tags published; three analytic-oracle reference tests green; pytest.
- **Depends-on:** T-100b

### T-100d Wire `fatigue_fem` through the enum + full ASTM/BS7608 corpus
- **Tier:** A
- **Money/reach rationale:** Mechanical + automotive fatigue life analysis. Completing fatigue_fem wiring unlocks durability/life estimates — a key simulation type for both personas.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `tools.py` enum for `fatigue` / `fatigue_fem`. Route to the fixed `fatigue_fem.py` (after T-100a). Add reference tests: S-N Wöhler curve fatigue life estimate for a steel specimen vs the BS 7608 / Miner's rule table (cite the specific table). Publish capability tag. Binary-absent → sentinel.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/tools.py`, `fatigue_fem.py`, `packages/kerf-fem/tests/test_fem_refvalues.py` (extend).
- **Definition of Done:** `run_fem(analysis_type='fatigue', ...)` executes; BS 7608 reference case matches to ±10%; capability tag published; pytest green.
- **Depends-on:** T-100a, T-100b

### T-100e CalculiX subprocess bridge + nonlinear contact reference corpus
- **Tier:** A
- **Money/reach rationale:** CalculiX is the reference nonlinear / contact solver for mechanical simulation depth (G-1 gap). The bridge lets Kerf hand off a complex nonlinear case to CalculiX when FEniCSx/internal is insufficient.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** A `calculix_bridge.py` module that translates a `KeRFJob` to CalculiX `.inp` format, invokes the `ccx` binary as a subprocess, parses the `.frd` result file, and maps results back to the Kerf result schema. Graceful sentinel when `ccx` is absent. Reference tests: a Hertzian contact case (two spheres) — peak pressure vs analytic Hertz formula; a nonlinear plasticity case — tip deflection vs analytic result. Mock the subprocess call for hermetic CI.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/calculix_bridge.py` (new), `packages/kerf-fem/tests/test_calculix_bridge.py` (mocked).
- **Definition of Done:** bridge translates a fixture job to `.inp`, parses `.frd` result; mock-subprocess test green; real-binary path documented; sentinel when absent; Hertz contact reference test green (with real binary in manual test, mocked in CI).
- **Depends-on:** T-100b

### T-100f Z88 subprocess bridge + modal / nonlinear reference corpus
- **Tier:** A
- **Money/reach rationale:** Z88Aurora is the reference for free/open-source linear + modal + nonlinear FEM (G-1 gap). A Z88 bridge gives Kerf a validated secondary solver for cross-checking results.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** A `z88_bridge.py` module that translates a `KeRFJob` to Z88 format (`.z88i1`/`.z88i2`), invokes the `z88r` binary as subprocess, parses the output, maps back. Graceful sentinel when absent. Reference test: a simply-supported beam modal (first natural frequency vs analytic Euler-Bernoulli). Mock the subprocess for hermetic CI.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/z88_bridge.py` (new), `packages/kerf-fem/tests/test_z88_bridge.py` (mocked).
- **Definition of Done:** bridge translates job → Z88 format, parses result; mock test green; sentinel when absent; modal reference frequency matches analytic to 1%.
- **Depends-on:** T-100b

### T-100g Mystran subprocess bridge + modal / aeroelastic reference corpus
- **Tier:** A
- **Money/reach rationale:** Mystran is the open-source Nastran-class solver for modal and aeroelastic analysis — a key gap for aerospace + automotive NVH. Bridge lets Kerf delegate complex aeroelastic cases.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** A `mystran_bridge.py` module that translates a `KeRFJob` to Nastran-format BDF (Mystran accepts standard Nastran BDF), invokes the `mystran` binary as subprocess, parses the `.F06` output, maps results back. Graceful sentinel when absent. Reference test: a cantilever plate first-mode frequency vs analytic thin-plate formula.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/mystran_bridge.py` (new), `packages/kerf-fem/tests/test_mystran_bridge.py` (mocked).
- **Definition of Done:** BDF translation correct for a fixture job; mock test green; sentinel when absent; first-mode reference frequency matches to 2%.
- **Depends-on:** T-100b

### T-100h FEM capability advertiser + LLM tool surface for all types
- **Tier:** A
- **Money/reach rationale:** The full FEM analysis suite is worthless if the LLM cannot discover and invoke it. This task makes every wired analysis type accessible from the chat interface.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `GET /health/capabilities` to advertise all active FEM analysis types (from T-100b/c/d). Update the `run_fem` LLM tool description and JSON schema so the LLM can enumerate available types and their required parameters. Add an `explain_fem_result` LLM tool that renders a plain-language summary of the result (displacement, stress, frequency, cycles) with citable values. Update `packages/kerf-fem/llm_docs/fem.md`.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/tools.py` (LLM tool surface), `packages/kerf-fem/llm_docs/fem.md`, `packages/kerf-api/` health endpoint, `packages/kerf-fem/tests/` (LLM tool dispatch tests).
- **Definition of Done:** `/health/capabilities` lists all wired types; `run_fem` tool accepts and routes all types; `explain_fem_result` produces a readable summary; LLM doc updated; dispatch tests green; pytest.
- **Depends-on:** T-100b, T-100c, T-100d

---

## CFD epic sub-tasks (T-101a … T-101f)

Decomposition of the T-101 umbrella. OpenFOAM is subprocess-invoked and unmodified;
graceful degrade when absent. All pure-Python solver work is hermetically testable
with analytic oracles.

### T-101a k-ε turbulence model with channel-flow reference oracle
- **Tier:** A
- **Money/reach rationale:** Turbulence modelling is the single biggest gap between the landed 2-D laminar foundation and CfdOF-class capability. Channel flow is the canonical k-ε validation case.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Implement the standard two-equation k-ε model (`cfd_ke.py`) with wall functions. Reference test: fully-developed turbulent channel flow (Re=10 000) — mean velocity profile vs the law-of-the-wall (u+ vs y+ in log region, slope κ=0.41, B=5.5) to within 5%. Pure Python + NumPy; no external solver. Analytic oracle only.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_ke.py` (new), `packages/kerf-fem/tests/test_cfd.py` (extend).
- **Definition of Done:** log-law region of the velocity profile matches the analytic wall law to 5%; y+ placement is in the log-layer; pytest analytic oracle; hermetic (no external binary).
- **Depends-on:** none

### T-101b k-ω SST turbulence model with backward-facing step reference
- **Tier:** A
- **Money/reach rationale:** k-ω SST is the industry-standard model for adverse pressure gradients (airfoils, external aero). Backward-facing step (Driver & Seegmiller) is the canonical SST reference case.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Implement the k-ω SST model (`cfd_kw_sst.py`) blending k-ω near-wall and k-ε in freestream. Reference test: backward-facing step reattachment length — computed vs experimental Driver & Seegmiller data (reattachment at ~7h step heights ± 15%). Analytic-oracle approximation based on the published correlation.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_kw_sst.py` (new), `packages/kerf-fem/tests/test_cfd.py` (extend).
- **Definition of Done:** reattachment length within 15% of the Driver & Seegmiller reference; wall shear stress sign change at the correct location; pytest; no external binary.
- **Depends-on:** T-101a

### T-101c 3-D unstructured mesh generator seed
- **Tier:** A
- **Money/reach rationale:** 3-D meshing is the prerequisite for any real-world CFD case (all practical flows are 3-D). Without a 3-D mesh, the solver depth above cannot be applied to real geometry.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** A `mesh3d.py` module that generates a structured hex or unstructured tet mesh around a simple geometry (box, sphere, cylinder) using a pure-Python Delaunay tet algorithm (or a thin wrapper around the `tetgen` binary with graceful degrade when absent). Output: a `Mesh3D` dataclass (vertices, elements, boundary-face tags). Reference test: tet mesh of a unit sphere — element count, minimum quality metric (Jacobian > 0 for all elements), and boundary face normals point outward.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/mesh3d.py` (new), `packages/kerf-fem/tests/test_mesh3d.py` (new).
- **Definition of Done:** unit sphere produces a valid tet mesh with no inverted elements; boundary normals point outward; Jacobian > 0 everywhere; tetgen-absent → graceful sentinel; pytest.
- **Depends-on:** none

### T-101d OpenFOAM bridge — case translation + subprocess + result parse
- **Tier:** A
- **Money/reach rationale:** OpenFOAM is the reference open-source CFD solver for serious 3-D turbulent flows (automotive aerodynamics, building wind load, duct flow). Bridging it gives Kerf CfdOF-class capability for those use-cases.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** `openfoam_bridge.py` — translate a `CFDJob` (geometry + boundary conditions + turbulence model + solver settings) to an OpenFOAM case directory structure (constant/, system/, 0/), invoke `blockMesh` + `simpleFoam` (or `rhoPimpleFoam`) as subprocesses, parse the `postProcessing/` result files, map back to the Kerf result schema. Graceful sentinel when the `simpleFoam` binary is absent. Mock the subprocess for hermetic CI. Reference test: lid-driven cavity at Re=1000 with the OpenFOAM path — compare u-velocity profile vs Ghia Re=1000 data (same oracle as the existing `cfd_navier_stokes.py` test but via the OF bridge).
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/openfoam_bridge.py` (new), `packages/kerf-fem/tests/test_openfoam_bridge.py` (mocked subprocess).
- **Definition of Done:** case directory written correctly; mock-subprocess test green; sentinel when absent; lid-driven cavity reference velocity profile matches to 5% with real binary in a manual test; pytest.
- **Depends-on:** T-101c

### T-101e CFD LLM tool surface + `analysis_type` enum extension
- **Tier:** A
- **Money/reach rationale:** Same rationale as T-100h — the CFD solver depth is invisible to the LLM until properly surfaced.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend the `run_cfd` LLM tool (or add one if absent) to accept `turbulence_model` (`ke` / `kw_sst` / `laminar`) and `solver` (`internal` / `openfoam`). Publish CFD capability tags in `GET /health/capabilities`. Add an `explain_cfd_result` LLM tool that summarises Cp, drag coefficient, wall shear stress in plain language. Update `packages/kerf-fem/llm_docs/cfd.md`.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/tools.py` (extend or add `run_cfd`), `packages/kerf-fem/llm_docs/cfd.md`, health endpoint, `packages/kerf-fem/tests/` (dispatch tests).
- **Definition of Done:** `run_cfd` routes to k-ε, k-ω SST, and OpenFOAM paths; `/health/capabilities` lists CFD types; `explain_cfd_result` readable summary; doc updated; dispatch tests green; pytest.
- **Depends-on:** T-101a, T-101b, T-101d

### T-101f CFD heat transfer — conjugate heat transfer + buoyancy-driven flow
- **Tier:** A
- **Money/reach rationale:** Thermal-CFD (electronics cooling, HVAC duct, building natural ventilation) is the most common CFD use-case outside aero. Adds heat transfer to the turbulent solver chain, covering electronics + architecture personas in addition to mechanical + automotive.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `cfd_navier_stokes.py` (or add `cfd_heat.py`) with the energy equation and buoyancy forcing (Boussinesq approximation). Reference test: differentially-heated vertical cavity (de Vahl Davis benchmark, Ra=10^4) — Nusselt number on the hot wall vs the published de Vahl Davis value (Nu≈2.243 ± 0.005). Pure Python; analytic oracle; no external binary.
- **Target files/packages:** `packages/kerf-fem/src/kerf_fem/cfd_heat.py` (new or extend), `packages/kerf-fem/tests/test_cfd.py` (extend).
- **Definition of Done:** de Vahl Davis Nu on hot wall within 2% of the published reference; temperature field has correct hot/cold wall gradient; pytest analytic oracle; hermetic.
- **Depends-on:** T-101a

---

## Geometry kernel P2 interop — T-NN tracking (T-156 … T-159)

The GK-NN backlog in `docs/plans/geometry-kernel-roadmap.md` tracks the detailed
kernel tasks. These T-NN entries cover the **P2 interop block** — the "next focus"
items called out in the kernel roadmap and ROADMAP §4 (pure-Python STEP/IGES,
SubD↔NURBS, mesh→NURBS autosurface, 2D region boolean) — giving them slots in the
main execution-order table. Each corresponds to GK-NN items; the GK file remains
the detailed spec; these T-NN entries are the execution-queue handles.

### T-156 GK P2: pure-Python STEP AP203/214 B-rep reader (GK-47)
- **Tier:** B
- **Money/reach rationale:** STEP is the universal mechanical exchange format. A pure-Python STEP reader decouples interop fidelity from OCCT, makes round-trip tests hermetic, and reduces the hard OCCT coupling for every persona. Cross-sector reach.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Pure-Python `geom/io/step_read.py` — parse STEP AP203/214 `ADVANCED_BREP_SHAPE_REPRESENTATION` into a `validate_body`-clean `Body`. Bounded to the primitive + filleted-box matrix initially. Opus-class task (GK-47 in the kernel plan); run as an isolated worktree on the opus spine. No OCCT; no external binaries; hermetic tests.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/geom/io/step_read.py` (new), `packages/kerf-cad-core/tests/test_step_io.py` (new).
- **Definition of Done:** read a STEP box (OCCT-exported fixture), `validate_body` ok, vertices match to `1e-9`; pytest hermetic (fixture file committed, no OCCT call in the test); ties GK-47.
- **Depends-on:** none

### T-157 GK P2: pure-Python STEP AP214 B-rep writer (GK-48)
- **Tier:** B
- **Money/reach rationale:** STEP writer closes the round-trip, enabling in-process Hausdorff oracle tests that currently require OCCT. Cross-sector interop depth.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Pure-Python `geom/io/step_write.py` — emit a `Body` as STEP AP214. Write→read round-trip Hausdorff ≤ `1e-7` on box/cyl/sphere/filleted-box matrix. Opus-class task (GK-48). No OCCT; no external binaries; hermetic tests.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/geom/io/step_write.py` (new), `packages/kerf-cad-core/tests/test_step_io.py` (extend).
- **Definition of Done:** write→read round-trip Hausdorff ≤ `1e-7` on the primitive + filleted-box matrix; pytest hermetic; ties GK-48.
- **Depends-on:** T-156

### T-158 GK P2: SubD cage → watertight NURBS Body bridge (GK-52/53)
- **Tier:** B
- **Money/reach rationale:** SubD↔NURBS is the missing bridge for jewelry (organic shapes), industrial design, and marine hull fairing — cross-sector quality signal that incumbents gate behind premium licenses.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** `geom/subd.py` extension — Catmull-Clark limit-surface → bicubic NURBS patch per quad face, sew patches into a watertight `Body` (extraordinary-point handling via a local G1 patch). Also the reverse: NURBS `Body` → SubD cage. Opus-class (GK-52/53); limit-surface deviation from Stam evaluation ≤ `1e-6`. No OCCT; hermetic tests.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/geom/subd.py` (extend), `geom/brep_build.py` / `geom/sew.py` (reuse), `packages/kerf-cad-core/tests/test_subd_nurbs.py` (new).
- **Definition of Done:** SubD cube → smooth `validate_body`-clean NURBS body; limit-surface deviation ≤ `1e-6` vs Stam; reverse round-trip for a cube returns original cage to `1e-7`; pytest; ties GK-52/53.
- **Depends-on:** none

### T-159 GK P2: 2D region boolean on planar curve loops (GK-56/57)
- **Tier:** B
- **Money/reach rationale:** 2D region boolean (sketch-driven solid extrude/pocket without OCCT) is the key enabler for a pure-Python parametric workflow that operates without the OCCT worker. Unlocks the full in-process sketch→solid path.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** `geom/region2d.py` — union/diff/intersection on planar closed curve loops with holes → `Face` with inner loops; then `extrude_to_body` with holes (washer, etc.). Reference: square − circle area = 1 − πr² exact; extruded washer volume = π(R²−r²)h exact; `validate_body` ok (genus per hole). Ties GK-56/57.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/geom/region2d.py` (new), `geom/brep_build.py` (reuse), `packages/kerf-cad-core/tests/test_region2d.py` (new).
- **Definition of Done:** square−circle area exact; extruded washer `validate_body` ok and volume exact; loop orientation CCW/CW per contract; pytest; ties GK-56/57.
- **Depends-on:** none

---

## P2 cross-cutting capabilities — new tasks (T-160 … T-164)

Unticketed P2 ROADMAP ambitions. Each is a moat-depth or platform-multiplier
item that has no task yet. Not P0/P1 blockers, but important for competitive
depth and listed in ROADMAP §3 P2 / §3.5.

### T-160 Real-time multi-user collaboration (operational transform / CRDT)
- **Tier:** B
- **Money/reach rationale:** Real-time collaboration is a top conversion argument for professional teams (mechanical/architecture/ECAD). Every sector benefits simultaneously — pure platform multiplier. Justifies Pro/Enterprise tier uplift. P2 moat.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Implement a real-time collaborative editing layer for parametric files (`.feature`, `.bim`, `.circuit.tsx`, `.sketch`) using a CRDT or OT approach. Each connected user sees others' edits in near-real-time. Conflicts resolve deterministically without lock-out. Presence indicators (cursor / selection) are a UX bonus but not the gate. Scope: text-native file kinds first (`.sketch`, `.equations`); binary/OCCT-evaluated files deferred to a follow-on. Backend: Postgres LISTEN/NOTIFY or a lightweight WebSocket broadcast per project. Frontend: merge received ops into the live editor state.
- **Target files/packages:** `packages/kerf-api/src/kerf_api/routes.py` (WebSocket collaboration endpoint), `packages/kerf-core/src/kerf_core/collab/` (new — OT/CRDT engine), `src/lib/collabClient.js` (new), `src/components/FileEditor.jsx` (op-merge wiring), tests.
- **Definition of Done:** two simulated users editing the same `.sketch` file concurrently converge to a consistent state (no lost edits, no divergence) after a simulated network round-trip; conflict resolution is deterministic; pytest + vitest on the merge logic.
- **Depends-on:** none

### T-161 GD&T / PMI model-based definition + homologation documentation
- **Tier:** A
- **Money/reach rationale:** GD&T MBD (product and manufacturing information embedded in the 3D model) is required for aerospace, automotive, and defence homologation. Mechanical + automotive personas (2 large paying workforces). GD&T frames already render; this task adds the standards-compliant MBD layer.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend the shipped GD&T callout system (T-27) into a full model-based definition package: (a) 3D tolerance annotations attached to `Body` faces/edges (not just drawings) readable as a structured MBD dataset; (b) `export_qif` LLM tool emitting a QIF (Quality Information Framework) XML containing all PMI annotations, suitable for CMM import; (c) a homologation document generator that extracts all datums + tolerances from the model and emits a structured report (PDF-ready via a templating step). Builds on the shipped `kerf_cad_core.gdt_callouts`.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/gdt_callouts/` (extend to 3D MBD), `packages/kerf-cad-core/src/kerf_cad_core/mbd.py` (new — MBD dataset), `packages/kerf-imports/src/kerf_imports/qif_writer.py` (new — QIF export), `packages/kerf-cad-core/llm_docs/mbd.md` (new), tests.
- **Definition of Done:** a model with datums + tolerances exports a valid QIF XML (validate against QIF schema); the homologation report lists all annotations in order; pytest with fixture model.
- **Depends-on:** T-27

### T-162 Generative / topology optimization — manufacturing constraints + multi-load (production-grade)
- **Tier:** A
- **Money/reach rationale:** Basic SIMP topo-opt is shipped (`packages/kerf-topo`). Production-grade generative design (manufacturing-constrained, multi-load-case, multi-objective, lattice-infill) is the moat item for mechanical + automotive (2 personas, ROADMAP §3.5). High AI-native leverage: the LLM frames objectives + constraints in text.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Extend `packages/kerf-topo` beyond the basic single-objective SIMP with: (a) manufacturing constraints — minimum member size, draw direction, symmetry planes; (b) multi-load-case envelope optimization (worst-case compliance over N load cases); (c) multi-objective Pareto front (stiffness vs mass vs manufacturability); (d) lattice-infill grading (variable density lattice inside the topology boundary). Each is additive to the FEniCSx SIMP core; do not rewrite the solver, extend it. Reference tests: compliance minimization with minimum-member-size constraint must produce a result with no features thinner than the specified minimum (verify via a thickness map). Cite ROADMAP §3.5 "production-grade" distinction from the basic shipped version.
- **Target files/packages:** `packages/kerf-topo/src/kerf_topo/` (constraints module, multi-load module, lattice module), `packages/kerf-topo/tests/` (extend).
- **Definition of Done:** multi-load optimization runs on 2+ load cases and produces a compliance envelope; minimum-member-size constraint produces verifiably thicker features; Pareto front returns 3+ non-dominated designs; lattice infill grading verified by density histogram; pytest with analytic or fixture-based references.
- **Depends-on:** none

### T-163 Robotics cell / kinematics / motion simulation seed
- **Tier:** A
- **Money/reach rationale:** Robotics programming (offline path generation, cell simulation, kinematics) is a growing manufacturing workforce segment with high AI-native fit (robot programs are text). 5-axis CAM (`packages/kerf-cam`) is an adjacent, reusable path-gen base. P2 moat (ROADMAP §3 P2).
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-robotics/` with: (a) a `RobotCell` data model (6-DOF serial robot with DH parameters, workspace, joint limits, end-effector); (b) forward kinematics (FK) and inverse kinematics (IK, analytic 6-DOF solution for common arm families: ABB, KUKA, Fanuc); (c) trajectory planning (point-to-point, linear, spline) with collision-free path via swept-volume check against a simple scene; (d) offline program generation for ABB RAPID / KUKA KRL / Fanuc LS. Reference tests: FK of a known configuration vs analytic; IK solve → FK round-trip to `1e-6`; RAPID output parses structurally. No simulation GUI in this task — numeric/programmatic only.
- **Target files/packages:** `packages/kerf-robotics/src/kerf_robotics/` (new package — `robot.py`, `kinematics.py`, `trajectory.py`, `codegen/rapid.py`, `codegen/krl.py`, `codegen/fanuc_ls.py`), `packages/kerf-robotics/tests/` (new), migration for `robot_cell` kind, `packages/kerf-robotics/llm_docs/robotics.md`.
- **Definition of Done:** FK/IK round-trip exact to `1e-6`; trajectory from A to B is collision-free against a simple box obstacle; RAPID/KRL/LS output are structurally valid programs; pytest analytic oracles.
- **Depends-on:** none

### T-164 1D system simulation seed — Modelica-compatible equation-based solver
- **Tier:** A
- **Money/reach rationale:** 1D system simulation (thermal / hydraulic / electrical / control networks) covers mechanical, electronics, and automotive ECU personas. Modelica is a declarative text-native language — the highest AI-native fit of any physics domain. ROADMAP §3.5 item; not yet ticketed. P2 moat.
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-sysmodel/` with: (a) a Modelica subset parser (`.mo` files — equations, components, connectors, basic standard library stubs: Electrical, Mechanical.Translational, Thermal); (b) a DAE (differential-algebraic equation) solver using `scipy.integrate.solve_ivp` with index reduction; (c) result visualisation via a `plot_sysmodel_result` LLM tool (time-series output); (d) an `explain_sysmodel_result` tool. Reference tests: RC circuit step response — time constant τ=RC exact; spring-mass-damper natural frequency vs analytic formula. No full MSL standard library — seed the subset needed for the reference tests only; `graceful-degrade` when `scipy` is absent. Cite `casadi` or `assimulo` as optional heavy-solver backends for the follow-on.
- **Target files/packages:** `packages/kerf-sysmodel/src/kerf_sysmodel/` (new — `parser.py`, `dae_solver.py`, `tools.py`), `packages/kerf-sysmodel/tests/` (new), `packages/kerf-sysmodel/llm_docs/sysmodel.md`.
- **Definition of Done:** RC circuit and spring-mass-damper references pass; DAE solver handles the reference models; Modelica-subset `.mo` file parses and simulates; `plot_sysmodel_result` returns a time-series dict; pytest analytic oracles; scipy-absent → sentinel.
- **Depends-on:** none

---

## P3 sector seeds — new tasks (T-165 … T-181)

Each is a proof-of-"we do everything" P3 seed: one bounded agent run that stands
up the minimal engine, data model, LLM tool, and analytic-oracle test for a new
sector. Establishes the foothold; deeper depth tasks follow in the same T-NN series.

### T-165 Plastics / injection-mold tooling seed
- **Tier:** A
- **Money/reach rationale:** Injection molding is one of the most common manufactured-parts workflows (mechanical + industrial design). Parting-surface + draft + rib design rules are rule-native — high AI-native fit.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-mold/` with: a `MoldDesign` data model (core/cavity, parting surface, ejector pins, gate location); a draft-analysis tool (reuse `surface_analysis.draft_angle_analysis` already shipped); a `check_moldability` LLM tool that checks minimum draft angle per face, maximum wall thickness uniformity, and parting-surface continuity; a `generate_parting_surface` helper that extends the parting line to a flat or ruled surface. Reference test: a simple box part → parting surface is flat and passes the draft-angle check.
- **Target files/packages:** `packages/kerf-mold/src/kerf_mold/` (new — `mold.py`, `tools.py`), `packages/kerf-mold/tests/` (new), `packages/kerf-mold/llm_docs/mold.md`, migration for `mold` kind.
- **Definition of Done:** a fixture box part generates a flat parting surface; `check_moldability` flags a zero-draft face; `generate_parting_surface` produces a ruled extension; pytest.
- **Depends-on:** none

### T-166 Packaging / dieline (folding carton + corrugated) seed
- **Tier:** B
- **Money/reach rationale:** Packaging design (folding carton, corrugated box) is a very large design workforce (retail, FMCG). Dieline is a flat-pattern problem — close to Kerf's sheet-metal unfold strength (T-2/T-3 shipped).
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-packaging/` with: a `Dieline` data model (panel + fold + cut + score lines on a 2D flat layout); parametric dieline generators for ECMA standard boxes (C-series RSC, A-series tray, B-series display); a `dieline_to_dxf` export reusing the shipped DXF writer (T-7); a `fold_dieline` 3D preview that sweeps panels along fold lines into a 3D carton shape. Reference test: ECMA C02 RSC box dimensions match standard; fold produces a closed 3D carton; DXF export round-trips.
- **Target files/packages:** `packages/kerf-packaging/src/kerf_packaging/` (new — `dieline.py`, `ecma_generators.py`, `fold.py`, `tools.py`), `packages/kerf-packaging/tests/`, `packages/kerf-packaging/llm_docs/packaging.md`, migration for `dieline` kind.
- **Definition of Done:** ECMA C02 generator produces correct panel dimensions; fold preview is a closed 3D shape; DXF round-trips; pytest.
- **Depends-on:** T-7

### T-167 Piping / P&ID / plant design seed
- **Tier:** A
- **Money/reach rationale:** Process piping + P&ID are a very large industrial engineering workforce (chemical, oil & gas, pharma). P&ID is symbol + connection = text-native. P3.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-piping/` with: a P&ID data model (instrument symbols, pipes, valves, vessels, tags per ISA 5.1 standard); a `piping_isometric` 3D route helper (orthogonal routing between equipment nozzles with standard pipe schedule elbow/tee library); a `pid_diagram` 2D layout exporter (DXF or SVG, symbols per ISA 5.1); an `import_pid` LLM tool that parses a text-format P&ID specification into the data model. Reference test: a simple 3-component loop (pump → vessel → HX) routes isometrically, produces correct elbow counts, and exports to DXF.
- **Target files/packages:** `packages/kerf-piping/src/kerf_piping/` (new — `pid.py`, `isometric.py`, `symbols.py`, `tools.py`), tests, llm_docs, migration for `pid` kind.
- **Definition of Done:** 3-component loop routes and produces the correct elbow/tee count; DXF export opens; `import_pid` round-trips a text spec; pytest.
- **Depends-on:** T-7

### T-168 Woodworking / furniture / joinery + cut list seed
- **Tier:** B
- **Money/reach rationale:** Woodworking / furniture design is a very large maker + small-business workforce (education, hobbyist, furniture makers). Cut list is the key deliverable. Close to Kerf's sheet-metal + nesting strength.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-woodworking/` with: a `WoodJoint` data model (mortise-and-tenon, dovetail, box joint, biscuit, pocket-screw, dowel — parametric per joint type); a `furniture_cutlist` tool that enumerates all solid parts into a cut list (species, thickness, width, length, qty, grain direction) from an assembly; a `joinery_feature` op that adds the correct geometry to mating parts; a `flat_pack_dieline` path for flat-pack furniture (reuse T-3 flat pattern + T-53 nesting). Reference test: a 4-leg table cut list has the correct part count + dimensions; mortise-and-tenon joint geometry is valid (tenon fits mortise with correct clearance).
- **Target files/packages:** `packages/kerf-woodworking/src/kerf_woodworking/` (new — `joints.py`, `cutlist.py`, `tools.py`), tests, llm_docs, migration for `woodwork` kind.
- **Definition of Done:** table cut list correct; M&T joint geometry passes clearance check; flat-pack path produces a DXF; pytest.
- **Depends-on:** T-3, T-53

### T-169 Optics / lens design seed (ray-trace paraxial model)
- **Tier:** B
- **Money/reach rationale:** Optical design (lens systems, telescopes, camera optics, illumination) is a niche but high-value technical workforce. Paraxial ray tracing is pure math — extremely AI-native. P3 / ROADMAP §3 scientific.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-optics/` with: a paraxial ray-transfer matrix (ABCD) model for multi-element thin-lens systems; a `trace_ray` LLM tool that traces a ray (or a bundle) through a lens system and returns spot size / focal length / aberration measures; a `lens_system` data model (element list: lens / mirror / aperture / detector); first-order aberration (Seidel coefficients). Reference tests: single thin lens — image distance matches 1/f = 1/do + 1/di exact; two-lens telephoto — EFL exact. No WASM / GPU; pure Python.
- **Target files/packages:** `packages/kerf-optics/src/kerf_optics/` (new — `ray_transfer.py`, `lens_system.py`, `tools.py`), tests, llm_docs, migration for `optics` kind.
- **Definition of Done:** thin-lens image distance exact; two-lens EFL exact; `trace_ray` returns spot diagram; pytest analytic oracles.
- **Depends-on:** none

### T-170 Watchmaking / horology seed (partsgen-reachable)
- **Tier:** B
- **Money/reach rationale:** Watchmaking is a high-margin niche (jewelry-adjacent) and partsgen-reachable (escapements, gear trains, springs are parametric). Strong AI-native fit: tolerances + counts are rule-driven.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-horology/` via `kerf-partsgen` pattern: parametric generators for Swiss lever escapement (escape wheel + pallet fork), gear train (wheel + pinion, module + tooth count), mainspring barrel. A `train_calculator` LLM tool that given target frequency + power reserve computes the gear-train ratios. Reference test: lever escapement escape wheel + pallet geometry generates valid involute tooth profiles; train_calculator ratio for 3 Hz + 48-hour reserve matches expected wheel-count solution.
- **Target files/packages:** `packages/kerf-partsgen/src/kerf_partsgen/generators/horology/` (new), `packages/kerf-horology/` (thin wrapper + tools), tests, llm_docs.
- **Definition of Done:** escape wheel + pallet fork geometry renders; tooth profile passes involute check; train_calculator produces correct ratio; pytest.
- **Depends-on:** none

### T-171 Dental CAD seed (crown + aligner + guide)
- **Tier:** A
- **Money/reach rationale:** Dental CAD (crowns, bridges, aligners, surgical guides) is a large and fast-growing clinical market with strong AI-fit (anatomy models are parametric once segmented). High-margin niche.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-dental/` with: a tooth-anatomy data model (crown, root, arch); a `crown_design` tool that produces a parametric crown surface from a margin line + opposing tooth profile; a `surgical_guide` helper that places a drill guide on a jaw model at specified implant angles; DICOM-to-mesh ingest (thin wrapper around `pydicom` + marching cubes, graceful degrade when absent). Reference test: a fixture crown margin line → a closed crown surface that passes `validate_body`; drill guide placement at specified angulation matches within 0.1°.
- **Target files/packages:** `packages/kerf-dental/src/kerf_dental/` (new — `crown.py`, `guide.py`, `dicom_ingest.py`, `tools.py`), tests, llm_docs, migration for `dental` kind.
- **Definition of Done:** crown surface is `validate_body`-clean; guide placement angle within 0.1°; DICOM ingest degrades gracefully when `pydicom` absent; pytest.
- **Depends-on:** none

### T-172 Marine / naval architecture depth (hydrostatics + stability)
- **Tier:** B
- **Money/reach rationale:** T-71 seeded hull fairing. This task adds the hydrostatics + stability analysis that a naval architect actually needs: displacement, metacentric height (GM), righting lever (GZ) curve, trim + heel. High technical value on top of the NURBS seed.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Extend `packages/kerf-cad-core/` (or a new `packages/kerf-naval/`) with: a `HullHydrostatics` module that computes displacement, LCB, VCB, BM, GM, and the GZ righting-lever curve at a series of heel angles via numerical integration over the hull surface; a `stability_report` LLM tool that summarises IMO A.749 criteria (minimum GM, GZ area, max GZ angle). Reference tests: a prismatic hull of known length/beam/draft → displacement = ρgV exact; rectangular barge GM = B²/12d exact.
- **Target files/packages:** `packages/kerf-naval/src/kerf_naval/hydrostatics.py` (new), `packages/kerf-naval/src/kerf_naval/stability.py` (new), `packages/kerf-naval/tests/`, `packages/kerf-naval/llm_docs/naval.md`.
- **Definition of Done:** prismatic hull displacement exact; rectangular barge GM exact; GZ curve has correct sign change at the angle of vanishing stability; pytest analytic oracles.
- **Depends-on:** T-71

### T-173 Aerospace composites ply/layup seed
- **Tier:** A
- **Money/reach rationale:** Composites design (aerospace, wind, automotive) is a large high-value workforce. Ply-book / laminate analysis is rule-native and AI-native. P3 / ROADMAP §3.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-composites/` with: a `LaminateLayup` data model (ply sequence, fibre orientation, material, thickness per ply); Classical Laminate Theory (CLT) solver for in-plane stiffness (A, B, D matrices) and failure analysis (Tsai-Wu, Tsai-Hill criteria); a `layup_analysis` LLM tool; drape simulation (simple flat-to-surface geodesic mapping). Reference tests: [0/90/0] symmetric laminate A-matrix vs analytic CLT formula; Tsai-Wu failure index for a known load case vs hand-calculated.
- **Target files/packages:** `packages/kerf-composites/src/kerf_composites/` (new — `layup.py`, `clt.py`, `failure.py`, `drape.py`, `tools.py`), tests, llm_docs, migration for `layup` kind.
- **Definition of Done:** A-matrix exact vs CLT formula; Tsai-Wu failure index matches hand-calc to 1%; drape map produces a flat→surface mapping; pytest analytic oracles.
- **Depends-on:** none

### T-174 Civil engine depth: horizontal/vertical alignment + corridor (G-1 next step)
- **Tier:** B
- **Money/reach rationale:** T-70 seeded CRS + TIN. The next civil engine increment is alignment (horizontal / vertical / corridor) — the core civil engineering workflow for roads and rail. P3 distinct engine.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Extend `packages/kerf-civil/` with: a `HorizontalAlignment` model (tangent, circular arc, spiral / clothoid transition) and a `VerticalAlignment` model (grade lines + vertical parabolic curves); a `Corridor` that sweeps the cross-section assembly (carriageway, berm, ditch) along the alignment and computes cut/fill volumes via the prismatoid formula; a `plan_and_profile_sheet` exporter (DXF plan + profile sheets). Reference tests: a horizontal curve of known radius → arc length exact; a corridor over a fixture TIN → cut volume matches prismatoid formula.
- **Target files/packages:** `packages/kerf-civil/src/kerf_civil/alignment.py` (new), `corridor.py` (new), `plan_profile.py` (new), tests, llm_docs.
- **Definition of Done:** arc length exact; corridor volume matches prismatoid to 1%; DXF plan-and-profile opens correctly; pytest.
- **Depends-on:** T-70

### T-175 Interior / space-planning / FF&E seed
- **Tier:** B
- **Money/reach rationale:** Interior design / space planning / FF&E scheduling is a large workforce closely tied to the architect persona (Revit/SketchUp/AutoCAD market). High AI-native fit: spatial rules + fixture schedules are text.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-interior/` with: a `SpacePlan` data model (rooms, furniture items, clearances, circulation paths); a `place_furniture` LLM tool that places FF&E from a catalogue respecting clearances and accessibility codes (ADA min turning circle); a `room_schedule` generator (area, occupancy, finish, fixture count); an `import_ff_e_catalogue` tool (CSV/JSON catalogue ingest). Reference test: a 4m × 5m bedroom with a king bed + wardrobe + desk passes ADA clearance check.
- **Target files/packages:** `packages/kerf-interior/src/kerf_interior/` (new — `spaceplan.py`, `furniture.py`, `schedule.py`, `tools.py`), tests, llm_docs, migration for `spaceplan` kind.
- **Definition of Done:** bedroom layout passes ADA clearance check; room schedule generates correct area + fixture count; fixture CSV catalogue ingests; pytest.
- **Depends-on:** none

### T-176 Structural RC / steel + rebar design seed
- **Tier:** A
- **Money/reach rationale:** Structural engineering (RC and steel design) is a very large and well-paying professional workforce (architects + structural engineers, both personas). Code-compliance is rule-native — high AI-native fit.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-structural/` with: a `BeamDesign` tool that checks an RC or steel beam for bending, shear, and deflection per ACI 318 (RC) or AISC 360 (steel); a `ColumnDesign` tool for buckling + combined loading; a `rebar_layout` generator that places rebar in an RC section per ACI 318 cover/spacing rules; a `connection_check` for a bolted/welded steel connection per AISC. Reference tests: simply-supported RC beam under UDL — bending moment = wL²/8 exact; ACI 318 rebar placement passes the minimum cover check.
- **Target files/packages:** `packages/kerf-structural/src/kerf_structural/` (new — `beam.py`, `column.py`, `rebar.py`, `connection.py`, `tools.py`), tests, llm_docs, migration for `structural` kind.
- **Definition of Done:** bending moment exact; ACI cover check passes for a valid layout and fails for an invalid one; steel beam shear check matches AISC LRFD formula; pytest analytic oracles.
- **Depends-on:** none

### T-177 Energy / daylight / acoustic analysis seed (BIM integration)
- **Tier:** B
- **Money/reach rationale:** Energy + daylight + acoustic analysis are increasingly mandatory in building design (building codes, LEED/BREEAM certification). Architecture persona depth; bridges to the BIM substrate.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-building-performance/` with: (a) an energy analysis stub that computes simplified UA-value heat loss for a building envelope from IFC materials + areas (compare to a reference ASHRAE 90.1 U-value limit); (b) a daylight factor (DF) calculator for a room using the BRE split-flux method; (c) a room acoustics RT60 estimator (Sabine formula + Eyring correction). Each as an LLM tool. Reference tests: DF for a room with a known window area matches BRE formula; RT60 for a concrete room matches Sabine to 5%.
- **Target files/packages:** `packages/kerf-building-performance/src/kerf_building_performance/` (new — `energy.py`, `daylight.py`, `acoustics.py`, `tools.py`), tests, llm_docs.
- **Definition of Done:** DF matches BRE formula; RT60 matches Sabine to 5%; UA heat-loss flags a below-code envelope; pytest analytic oracles.
- **Depends-on:** none

### T-178 Landscape / site design seed
- **Tier:** B
- **Money/reach rationale:** Landscape architecture + site design is a distinct design discipline with its own tools (Vectorworks Landmark, AutoCAD Civil 3D landscape). Bridges T-70 civil TIN + BIM site (T-114).
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-landscape/` with: a `LandscapePlan` data model (planting zones, paths, grading contours, irrigation zones, hardscape areas); a `plant_schedule` generator (species, qty, size, location); a `grading_plan` tool that generates cut/fill contours from a design surface over a T-70 TIN terrain; an `irrigation_layout` helper (emitter placement + flow calculation). Reference test: a simple graded park site → cut/fill volume matches the T-70 prismatoid; plant schedule counts match the layout.
- **Target files/packages:** `packages/kerf-landscape/src/kerf_landscape/` (new), tests, llm_docs, migration for `landscape` kind.
- **Definition of Done:** grading cut/fill matches prismatoid; plant schedule count matches layout; irrigation total flow adds up; pytest.
- **Depends-on:** T-70

### T-179 Apparel / pattern-making seed (2D flat + seam allowance)
- **Tier:** B
- **Money/reach rationale:** Apparel pattern-making is one of the world's largest design workforces. Pattern-making is a 2D flat-geometry problem (parametric + rules) with a drape simulation extension. P3 / ROADMAP §3 soft-goods.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-apparel/` with: a `Sewing_Pattern` data model (panels, seam lines, grain lines, notches, seam allowance); parametric pattern generators for a basic bodice block + sleeve block + trouser block (size grading from measurements); a `grade_pattern` tool that scales from one size to another; a `seam_allowance_offset` tool (reuse the shipped `offset.py` curve-offset with self-intersection trim); a `pattern_marker` tool that bins panels into a fabric roll width (reuse T-53 nesting). Reference test: bodice block for a given bust measurement generates correct dart position per standard block formula; seam offset at the correct distance.
- **Target files/packages:** `packages/kerf-apparel/src/kerf_apparel/` (new — `pattern.py`, `blocks.py`, `grading.py`, `tools.py`), tests, llm_docs, migration for `pattern` kind.
- **Definition of Done:** bodice dart position matches standard formula; seam offset distance exact; marker bins panels within roll width; pytest.
- **Depends-on:** T-53

### T-180 Microfluidics / MEMS design seed
- **Tier:** B
- **Money/reach rationale:** Microfluidics / MEMS is a high-value niche (lab-on-chip, medical diagnostics, sensors). Channel design + fabrication rules are text-native. P3 / ROADMAP §3 scientific/niche.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-microfluidics/` with: a `MicrofluidicChip` data model (channels, chambers, inlets/outlets, electrodes, heaters — dimensions in µm); a `channel_flow` tool that computes pressure drop and flow resistance for a rectangular microchannel via the Hagen-Poiseuille formula (and the aspect-ratio correction for rectangular cross-sections); a `mixer_design` helper for passive T-mixer + serpentine mixer geometries; a `fabrication_check` tool that verifies minimum feature size + aspect ratio against soft-lithography design rules. Reference tests: Hagen-Poiseuille pressure drop for a rectangular 100 µm × 50 µm × 10 mm channel vs analytic formula.
- **Target files/packages:** `packages/kerf-microfluidics/src/kerf_microfluidics/` (new — `chip.py`, `flow.py`, `mixer.py`, `fab_check.py`, `tools.py`), tests, llm_docs, migration for `microfluidics` kind.
- **Definition of Done:** channel pressure drop matches Hagen-Poiseuille to 1%; aspect-ratio correction within 2%; fab check flags a too-narrow feature; pytest analytic oracles.
- **Depends-on:** none

### T-181 HVAC duct fabrication seed
- **Tier:** B
- **Money/reach rationale:** HVAC duct fabrication (sheet-metal ductwork for commercial buildings) bridges the BIM (T-113/T-114) and sheet-metal (T-1..T-4) substrates. Large fabrication workforce; duct fitting geometry is rule-native.
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Seed `packages/kerf-hvac/` with: a `DuctSystem` data model (rectangular/round/oval ducts, fittings — elbow, reducer, tee, cap, flex connector); a `duct_sizing` LLM tool (velocity method: select duct size for a target airflow + max velocity, citing ASHRAE duct-design guidelines); a `duct_flat_pattern` that generates the sheet-metal flat pattern for standard fittings (rectangular elbow, reducer) reusing the T-2/T-3 unfold path; a `pressure_loss` calculator (major friction loss + minor losses for fittings via ASHRAE HVAC Fundamentals coefficients). Reference tests: pressure drop for a straight rectangular duct matches Darcy-Weisbach formula; reducer flat pattern has the correct developed length.
- **Target files/packages:** `packages/kerf-hvac/src/kerf_hvac/` (new — `duct.py`, `sizing.py`, `flat_pattern.py`, `pressure.py`, `tools.py`), tests, llm_docs, migration for `duct` kind.
- **Definition of Done:** Darcy-Weisbach pressure drop matches to 1%; reducer flat pattern has correct developed length (analytic); duct sizing for a fixture flow produces a valid dimension; pytest analytic oracles.
- **Depends-on:** T-3

### T-182 Landing + Domains + Comparison matrix — surface the new sectors
- **Tier:** B
- **Money/reach rationale:** every new domain shipped this session
  (aerospace composites, dental, optics, horology, piping, packaging,
  mold/plastics, civil, marine, woodworking, …) is invisible to visitors
  until it appears on the Landing page + the Domains hub. Top-of-funnel
  discoverability for the entire feature sweep.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add the newly-shipped sectors to `src/routes/Landing.jsx`
  and the Domains hub/pages (`src/routes/domains/`) in the SAME style as
  the existing domains (Mechanical/Electronics/Architecture/Jewelry/
  Automotive) — cards/links + per-domain blurbs as the existing pattern
  dictates. ALSO update the competitor comparison matrix/pages
  (`src/routes/compare/`) so every new sector appears there too,
  consistent with the existing rows. Frontend only.
- **Target files/packages:** `src/routes/Landing.jsx`,
  `src/routes/domains/`, `src/routes/compare/`
  (+ `groupTaxonomy.js`/nav if needed), vitest.
- **Definition of Done:** Landing + Domains + the comparison matrix
  list every shipped sector; vitest on any pure helper; `npm run build`
  clean. UI change — needs user dev verification.
- **Depends-on:** the sector seeds (T-165..T-181) landed

## Save model + git polish (T-183 … T-188) — PRIORITY

These tickets land the full "local autosave + actual git save" model
plus the cloud-git polish gaps that are not yet ticketed. Three explicit
rings of safety: **L1** browser IndexedDB stash (crash-proof), **L2**
server `file_revisions` autosave (fine-grained undo), **L3**
`cloud_git_commits` (deliberate + safety-net squash, mirrored to
GitHub/GitLab). All P1 — user said "very important all the git stuff
must be in place".

### T-183 L1 — IndexedDB local stash (crash-proof working copy)
- **Tier:** B
- **Money/reach rationale:** localStorage's ~5–10 MB origin cap blows
  out the first time anyone opens a non-trivial CAD project; IDB gives
  us gigabytes of structured async storage. With L1 in place, the
  user's tab can crash, lose power, or be closed mid-edit and nothing
  is lost — this is the floor under every subsequent trust message we
  send about the L2/L3 rings.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** introduce `src/lib/localStash.js` wrapping IndexedDB
  (object store keyed by `workspaceId+filePath` → `{bytes, mtime,
  flushedToL2: boolean}`). Editor hooks (Monaco onChange, sketcher
  commit, feature-tree edit) debounce-write to L1 (1–3 s). On app load
  for a project, reconcile L1 against the server: anything with
  `flushedToL2=false` is re-POSTed via the existing save endpoint, then
  marked flushed. `beforeunload` guard fires ONLY when any IDB entry
  has `flushedToL2=false` (the genuine "might be lost on close" case).
  Add a Zustand selector `useDirtyL1Count()` for the toolbar dot.
- **Target files/packages:** `src/lib/localStash.js` (new),
  `src/stores/dirtyStore.js` (new), wire into `src/components/Editor*`
  + sketcher save path + feature-tree commit, `src/main.jsx` for the
  load-time reconcile + `beforeunload`. Vitest (fake-indexeddb).
- **Definition of Done:** killing the dev tab mid-edit restores
  on reload; `beforeunload` does not fire when L1 is clean even if
  L3 has uncommitted L2 revisions; reconcile is idempotent; vitest
  green; `npm run build` clean.
- **Depends-on:** none

### T-184 L2 — server autosave throttle dial-in + status surface
- **Tier:** B
- **Money/reach rationale:** the OSS `file_revisions` write path
  already exists, but the cadence is ad-hoc per editor. Formalising it
  (idle + interval) gives users a predictable "your work is saved"
  signal and stops accidental write storms during fast-drag edits.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** introduce `src/lib/autosaveScheduler.js` — exposes
  `markDirty(workspaceId, filePath)` + a shared scheduler that flushes
  to L2 (the existing `POST /workspaces/{id}/files/{path}` revision
  endpoint) on idle (after 2 s of no edits) OR on a hard interval
  (every 30 s while dirty). On success, flips the L1 entry to
  `flushedToL2=true` so the `beforeunload` guard relaxes. Emits
  `autosave-status` events the toolbar dot consumes: `dirty | saving |
  saved | error`. Backend already supports it — no API change.
- **Target files/packages:** `src/lib/autosaveScheduler.js` (new),
  `src/components/AutosaveStatus.jsx` (new — the toolbar dot),
  vitest + existing route tests cover the wire-up.
- **Definition of Done:** edits flush within 2 s idle / 30 s active;
  `file_revisions` rows appear at the right cadence; the dot reflects
  the four states; vitest green.
- **Depends-on:** T-183 (uses the L1 flushedToL2 flag)

### T-185 L3 — auto-commit safety net + dirty-time warning
- **Tier:** B
- **Money/reach rationale:** the user said "warn users of unsaved
  changes" — the right interpretation is **uncommitted** changes (L2
  rows that haven't been squashed into a `cloud_git_commits` row).
  This ticket makes git-saving the durable default without flooding
  the commit graph: deliberate commits get the user's message and the
  ◯ marker, the safety-net squashes silent autosave commits every N
  minutes of dirty L2 with the ◌ marker.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** backend — extend `packages/kerf-core/src/kerf_core/
  storage/materialize.py` with `auto_commit_if_idle(workspace_id, *,
  idle_minutes=15)` that finds the last `cloud_git_commits` row for
  the workspace, checks whether any `file_revisions` rows exist after
  it, and if `idle_minutes` have passed without a deliberate commit,
  writes a squashed auto-commit (`message="autosave " +
  iso_utc_now()`, `kind='autosave'`) using the existing
  `materialize_and_commit()` path. Add a `kind` column to
  `cloud_git_commits` (`enum('manual','autosave')`) — fold into
  `0012_cloud_git.sql` baseline; NO alter-shim. Scheduler: a periodic
  task (Postgres `LISTEN` or a 60-s poller in `kerf-server`). Frontend
  — extend the git graph (T-148) to render ◯ vs ◌; add a gentle
  banner that appears at 30 min uncommitted ("It's been a while — save
  a version?") with a one-click Commit button.
- **Target files/packages:** `packages/kerf-core/src/kerf_core/
  storage/materialize.py`, `packages/kerf-cloud/src/kerf_cloud/
  scheduler/auto_commit.py` (new), `packages/kerf-core/src/kerf_core/
  db/migrations/0012_cloud_git.sql` (fold `kind` column), `src/
  components/GitGraph.jsx`, `src/components/UncommittedBanner.jsx`
  (new), `src/lib/dirtyTimer.js`. Pytest + vitest.
- **Definition of Done:** with no deliberate commit, an autosave
  appears at the configured interval; deliberate commits are
  unaffected; graph distinguishes them; banner appears + dismisses
  cleanly; baseline migration includes `kind`; pytest + vitest green;
  `npm run build` clean.
- **Depends-on:** T-184 (needs reliable L2 cadence to detect "dirty"),
  T-148 (graph rendering)

### T-186 L3 — PR-style file diff + large-file accept-yours/theirs UX
- **Tier:** B
- **Money/reach rationale:** T-148 ships the DAG but you cannot SEE
  what changed in a commit. Without a review surface, "save to git" is
  trust-fall. For text files (Python, ladder, gcode, SVG paths)
  a per-file text diff is the obvious move. **For large binary files
  (STEP, occt-stream, jewelry presets) a real diff is meaningless** —
  the right UX is a 3D preview-side-by-side ("yours" left, "theirs"
  right) + an explicit **Accept yours / Accept theirs** button per
  file. This ticket adds both surfaces.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** backend — `GET /workspaces/{id}/git/commits/{sha}/diff`
  returns a JSON manifest: per-file `{path, kind, change:
  added|modified|deleted, text_diff?: unified, oid_old?, oid_new?,
  binary?: bool, preview_thumb_url?}`. Reuses the LFS pointer +
  `read_path` hydrate (T-124) to get both sides. Frontend — a new
  `src/components/CommitDiff.jsx` that hangs off the T-148 graph: on
  click, opens a per-commit pane listing files; text files render via
  the existing Monaco diff editor; **binary/large files render a
  split-pane preview** (3D Renderer instances for STEP / occt-stream,
  image thumbs for raster, "no preview available" for opaque blobs)
  with a per-file **Accept yours · Accept theirs** action that POSTs
  back a resolve-merge-conflict commit. No three-way text merge UI in
  this ticket — explicit, file-level pick is the contract.
- **Target files/packages:** `packages/kerf-api/src/kerf_api/
  routes_git.py` (new diff endpoint + accept-resolve endpoint),
  `packages/kerf-core/src/kerf_core/storage/diff.py` (new — classify
  + unified-diff for textual, side-list for binary),
  `src/components/CommitDiff.jsx`, `src/components/GitGraph.jsx`
  (wire), `src/components/BinarySideBySide.jsx` (new), pytest +
  vitest + an e2e walk through "open commit → see diff → accept
  theirs on a STEP file → graph shows the resolve commit".
- **Definition of Done:** opening any commit in the graph shows the
  per-file list; text diffs render; binary files show side-by-side
  previews with accept-yours/theirs that actually writes a resolve
  commit; no `alter table` shims (diff is read-only); pytest + vitest
  + e2e green.
- **Depends-on:** T-148, T-124 (materialize/read_path), T-150 (oracle
  used to keep both oids reachable)

### T-187 L3 — onboarding doc: "your work is safe in three places"
- **Tier:** B
- **Money/reach rationale:** silent autosave is only trustworthy if
  users believe in it. A single concise docs page explaining the L1
  (IDB) / L2 (revisions) / L3 (git commits) model — with screenshots
  of the toolbar dot, the graph markers (◯ vs ◌), and the banner —
  converts the architecture into a trust message.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add `public/docs/saving-your-work.md` (or wherever the
  existing docs viewer reads from — check `public/docs-manifest.json`)
  with the 3-ring explanation, the dot states, the graph markers,
  what `beforeunload` fires on, what the banner means, where
  GitHub/GitLab sync (T-144/T-145) plugs in. Link from the empty
  state of the Git panel + from Settings → Account. Docs viewer must
  still render it (regenerate `docs-manifest.json` via existing
  script — but DON'T commit `public/docs-manifest.json` per repo
  rule).
- **Target files/packages:** `public/docs/saving-your-work.md` (new),
  link references in `src/components/GitPanel*`,
  `src/routes/Settings*` (link only). Vitest.
- **Definition of Done:** doc renders in the in-app viewer;
  screenshots not required (user will dev-verify); navigation links
  present; vitest green; `npm run build` clean.
- **Depends-on:** T-183..T-186 (so the doc describes the real model)

### T-188 Cloud-git ops polish — per-project packfile GC + GitLab env wiring guide
- **Tier:** B
- **Money/reach rationale:** the blob ledger GC (T-150) tracks LFS
  blobs, but the per-project bare repos themselves accumulate loose
  objects + packfiles under Tigris. Without periodic `git
  repack`/`gc`, storage cost creeps linearly per project. Separately,
  T-145 supports GitLab but production env vars (`cloud_gitlab_app_id`
  / `app_secret` / `host`) are not wired in the deploy doc — they're
  ops, not code.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** introduce `packages/kerf-cloud/src/kerf_cloud/git_gc.py`
  with `repack_project(workspace_id)` that calls pygit2 / `git repack
  -ad` against the S3-backed repo (use the T-125 `S3GitStorer.
  for_project` factory). Scheduler entry: run weekly per
  recently-active project (cap concurrency at 2). Add a quota readout
  CLI: `kerf admin repo-size <workspace>` reads packfile + LFS
  blob sizes from the ledger. Docs: extend the self-host README with
  the GitLab env-var section (`cloud_gitlab_app_id`,
  `cloud_gitlab_app_secret`, `cloud_gitlab_host`) and the matching
  GitHub variables.
- **Target files/packages:** `packages/kerf-cloud/src/kerf_cloud/
  git_gc.py` (new), `packages/kerf-cloud/src/kerf_cloud/scheduler/
  git_gc_runner.py` (new), `packages/kerf-cli/src/kerf_cli/admin.py`
  (extend), README/self-host docs.
- **Definition of Done:** `repack_project()` reduces loose-object
  count on a synthetic repo; scheduler entry registered; CLI prints
  byte totals; pytest green; docs section added.
- **Depends-on:** T-125, T-145, T-150


## Electronics authoring depth (T-189 … T-198)

User-requested 2026-05-18 — improve tscircuit editing (wires, placement, ratsnest, footprints, viewer-on-LLM-output) AND add atopile as a peer textual authoring path. Convergence: atopile compiles → KiCad netlist → Circuit JSON; tscircuit also targets Circuit JSON; KiCad / Circuit JSON is the shared canonical form; tscircuit's web renderer is the viewer for both.

### T-189 tscircuit wire-routing — interactive editor wire drag + nudge
- **Tier:** A
- **Money/reach rationale:** the tscircuit canvas already renders the board (T-77 family); the gap is *editing* — users currently cannot drag a wire to nudge it around a part. Closes a daily-driver hole for the electronics persona.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add a wire-drag interaction mode to `src/components/CircuitCanvas*` (find by grep). On wire-drag: hit-test the wire segment, capture pointer, update the segment's anchor points, re-emit the patched Circuit JSON. Right-click on a wire opens a context menu: "delete · convert to bus · pin to grid · re-route". Frontend only (the Circuit JSON layer is already round-trippable).
- **Target files/packages:** `src/components/CircuitCanvas/wireEdit.js` (NEW), `src/components/CircuitCanvas/ContextMenu.jsx` (NEW), wire into the existing canvas component (additive only), vitest.
- **Definition of Done:** dragging a wire updates its routing and the Circuit JSON; right-click menu actions all work; vitest on the pure helpers; `npm run build` clean.
- **Depends-on:** none

### T-190 tscircuit footprint placement — drag/snap/rotate library parts
- **Tier:** A
- **Money/reach rationale:** placing parts is the second-most-common operation after wiring; today users have to author tscircuit JSX. A direct-manipulation footprint placer matches the KiCad / Altium / EasyEDA expectation and removes a major friction point.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** sidebar component library (read from `@tscircuit/footprinter`'s catalogue); drag a footprint onto the canvas → ghost preview with the bounding box + pad outlines → drop emits a `source_component` + `pcb_component` + `schematic_component` triplet into the Circuit JSON. Rotation via `R` key (90° increments). Snap to a configurable grid (default 0.5 mm). Multi-select + group move.
- **Target files/packages:** `src/components/CircuitCanvas/FootprintLibrary.jsx` (NEW), `src/components/CircuitCanvas/PlacementMode.jsx` (NEW), `src/lib/circuitJsonPatch.js` (NEW — additive Circuit JSON mutation helpers), vitest.
- **Definition of Done:** drag any `@tscircuit/footprinter`-known footprint onto the canvas, rotate it, move it, undo — Circuit JSON round-trips clean; vitest; `npm run build` clean.
- **Depends-on:** T-189 (shared canvas helpers)

### T-191 tscircuit ratsnest + DRC live overlay
- **Tier:** A
- **Money/reach rationale:** ratsnest (unrouted-net guide lines) + a live design-rule check (clearance / acid-trap / via-in-pad) are the two visual feedback layers that turn a PCB editor from "viewer" into "tool". KiCad has both — tscircuit's renderer doesn't.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** compute ratsnest in pure Python (`packages/kerf-electronics/src/kerf_electronics/ratsnest.py`) — minimum-spanning-tree over each net's pad positions; frontend overlays the airline segments. DRC: clearance check (pad-to-pad, pad-to-trace, trace-to-trace), unconnected pads, missing footprint. Frontend renders DRC violations as red highlights on the offending features.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/ratsnest.py` (NEW), `packages/kerf-electronics/src/kerf_electronics/drc.py` (NEW), `packages/kerf-electronics/tests/test_ratsnest.py` + `test_drc.py`, `src/components/CircuitCanvas/RatsnestLayer.jsx` (NEW), `src/components/CircuitCanvas/DRCOverlay.jsx` (NEW).
- **Definition of Done:** ratsnest tree connects every net's pads with minimum total length (analytic MST oracle); DRC fires on a known-violating fixture; frontend overlay renders; pytest + vitest green.
- **Depends-on:** none

### T-192 tscircuit LLM-output viewer — render any Circuit JSON the chat returns
- **Tier:** A
- **Money/reach rationale:** today when the LLM emits Circuit JSON in chat (e.g. `make_circuit` tool result), it shows as raw text — the user has to copy/paste into a file to see it. A native viewer turns every chat message into a live preview, hugely amplifying the LLM-electronics loop.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** in the chat message renderer (grep `src/components/Chat*`), detect Circuit JSON in code-blocks (`json` fence with a tscircuit shape — heuristic: top-level `circuit_json` key or array of objects with `type: "source_component"|"pcb_*"|"schematic_*"`). Render an inline `<CircuitCanvasMini>` (read-only, no editing) below the code block. One-click "Open in editor" button writes it to a new file in the project.
- **Target files/packages:** `src/components/Chat/CircuitJsonPreview.jsx` (NEW), `src/lib/detectCircuitJson.js` (NEW), wire into the chat message renderer (additive only). Vitest.
- **Definition of Done:** chat messages containing Circuit JSON render an inline preview; "Open in editor" creates a new project file; vitest detects + non-detects; `npm run build` clean.
- **Depends-on:** none

### T-193 tscircuit ↔ KiCad / Circuit-JSON canonical-form bridge
- **Tier:** B
- **Money/reach rationale:** Circuit JSON is tscircuit's intermediate; KiCad netlist is the industry exchange. A robust bidirectional bridge means both authoring paths (tscircuit JSX + atopile-as-of-T-194) land on the same fabricable artefact and users can take the design to any house.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** `packages/kerf-electronics/src/kerf_electronics/kicad_io.py` (NEW) — write Circuit JSON → KiCad `.kicad_pcb` + `.kicad_sch` (v6/v7 format) and read back. The "write" path is the priority (export to fabrication); the "read" path is the bonus (import an existing KiCad project into Kerf). Pytest oracle: round-trip a synthetic 2-resistor Circuit JSON through KiCad export + re-import → node count + net count + footprint refs preserved.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/kicad_io.py`, `packages/kerf-electronics/tests/test_kicad_io.py`, fixtures dir.
- **Definition of Done:** Circuit JSON → KiCad → Circuit JSON round-trip preserves nodes/nets/footprints; pytest green; `npm run build` clean.
- **Depends-on:** none

### T-194 atopile parser + AST — pure-Python read of `.ato` source
- **Tier:** A
- **Money/reach rationale:** atopile (textual, code-like electronics authoring) is the fastest-growing alt-flow to tscircuit. Adding it gives Kerf a SECOND authoring surface that both compile to the same Circuit JSON / KiCad netlist — broadens the funnel to firmware/embedded engineers who think in code, not schematics.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** `packages/kerf-electronics/src/kerf_electronics/atopile/parser.py` — pure-Python parser for the atopile `.ato` syntax (modules, components, connections, units, parameters); emit an AST. Mirror the subset documented at atopile.io as of 2025. Tokenizer + LR/PEG parser (no external deps; hand-rolled).
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/atopile/parser.py` (NEW), `packages/kerf-electronics/src/kerf_electronics/atopile/ast.py` (NEW dataclass tree), `packages/kerf-electronics/tests/test_atopile_parser.py` + a fixtures dir with 4–5 small `.ato` files (resistor, voltage-divider, RC-filter, LED-driver).
- **Definition of Done:** all 4 fixtures parse to a non-empty AST; AST nodes carry source-location info; pytest oracles assert connection counts; `npm run build` clean.
- **Depends-on:** none

### T-195 atopile → Circuit JSON / KiCad compiler
- **Tier:** A
- **Money/reach rationale:** parsing is the seed; compiling is the value. Once atopile AST → Circuit JSON works, every atopile file is renderable in Kerf's tscircuit canvas + exportable via T-193 to KiCad.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** `packages/kerf-electronics/src/kerf_electronics/atopile/compile.py` — walk the AST, resolve modules, expand parameters, emit Circuit JSON. Use the existing footprint catalogue from `@tscircuit/footprinter` (read its index via a small Python adapter, OR shell out to node — discuss in the agent's commit message). KiCad netlist emission is delegated to T-193's `kicad_io.py` (consume its writer; do NOT modify it).
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/atopile/compile.py`, `packages/kerf-electronics/tests/test_atopile_compile.py`.
- **Definition of Done:** voltage-divider fixture compiles to Circuit JSON with 2 resistors + 3 nets; LED-driver compiles to working netlist; round-trip via T-193 to KiCad preserves topology; pytest green.
- **Depends-on:** T-194, T-193

### T-196 atopile editor + viewer in the IDE
- **Tier:** A
- **Money/reach rationale:** authoring needs an editor surface. A Monaco panel for `.ato` files + the live Circuit JSON canvas alongside (read-only mirror of T-189/T-190's canvas) gives atopile users the same loop as tscircuit users.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Monaco language-mode for `.ato` (tokenizer + syntax highlighting; no LSP yet). A split-pane editor: text on the left, live `<CircuitCanvasMini>` on the right showing the compiled Circuit JSON; debounced recompile on edit. Errors in the text panel show a red squiggle (from T-194 parser errors).
- **Target files/packages:** `src/components/AtopileEditor.jsx` (NEW), `src/lib/atopileMonacoLanguage.js` (NEW), `src/lib/atopileCompileBridge.js` (NEW — calls the backend compile endpoint), API route to expose T-195's compiler over HTTP.
- **Definition of Done:** editing a `.ato` file in the IDE shows live syntax highlight + a live Circuit JSON preview; error squiggles on a deliberately broken sample; vitest on pure helpers; `npm run build` clean.
- **Depends-on:** T-194, T-195

### T-197 atopile component-library bridge — JLCPCB / SnapEDA / Octopart
- **Tier:** B
- **Money/reach rationale:** atopile's value compounds when components resolve to real parts on real distributors. Bridge into the existing distributor surface (T-49 family) so an `.ato` module declaring `R1 = Resistor(value=10k)` resolves to a real JLCPCB / DigiKey part with footprint.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** extend `packages/kerf-electronics/src/kerf_electronics/atopile/library.py` (NEW) — given an atopile `Component(...)` declaration, query the existing distributor catalogue (kerf-cloud or local cache), return the best-match `mfr_part + footprint + datasheet_url`. Bind into the T-195 compiler so the emitted Circuit JSON carries real distributor refs.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/atopile/library.py`, `packages/kerf-electronics/tests/test_atopile_library.py`.
- **Definition of Done:** voltage-divider with `value=10k, package=0603` resolves to a real JLCPCB part (mocked in tests via fixture); fallback to "unresolved" warning when no match; pytest green.
- **Depends-on:** T-195

### T-198 atopile LLM authoring — generate `.ato` from a prompt
- **Tier:** B
- **Money/reach rationale:** code-first electronics + LLM ≈ Cursor-for-PCB. The LLM emits `.ato`, the user previews the compiled Circuit JSON (T-196), iterates. Closes the "tell me what you want, get a working PCB" loop.
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add an LLM tool `make_atopile` to the existing tool registry — input: textual spec ("voltage divider, 10k+1k, 5V in, 0.45V out") → output: a `.ato` source string. Validate via T-194 parser before returning. The LLM tool docs (`llm_docs/atopile.md`) live in `kerf-electronics`.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/atopile/llm.py`, `packages/kerf-electronics/llm_docs/atopile.md`, `packages/kerf-electronics/tests/test_atopile_llm.py`.
- **Definition of Done:** `make_atopile("voltage divider")` returns a parseable `.ato`; `make_atopile("RC low-pass 10kHz cutoff")` returns parseable + the cutoff value embedded as a parameter; pytest green.
- **Depends-on:** T-194

## Electronics authoring strategy (T-199 … T-203) — atopile + tscircuit pair

User-direction 2026-05-18: ship the "two authoring styles, one fabrication target" stance. atopile and tscircuit converge at Circuit JSON / KiCad; we keep both because cognitive style differs (EE-code-first vs maker-visual-first). UI segregates by file extension; one renderer; one IR.

### T-199 New-file dialog adds `.ato`; extension → editor routing
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Surface `.ato` as a first-class file-type in the new-file dialog alongside `.tsx` / `.py` / `.md`. Add a small extension-router (`.ato` → `<AtopileEditor>` from T-196; `.tsx` → the existing tscircuit/JSX editor; everything else falls through to the default Monaco editor). Frontend only.
- **Target files/packages:** `src/components/NewFileDialog.jsx` (additive only; preserve existing options), `src/lib/editorRouter.js` (NEW pure-logic), `src/components/EditorHost.jsx` if present (one-line additive `if (ext==='ato')`), vitest.
- **Definition of Done:** new-file dialog shows a labelled "Atopile (.ato)" choice and creates a `module Foo: ... end Foo;` skeleton; opening any `.ato` file routes to AtopileEditor; opening `.tsx` still goes to the tscircuit editor; vitest on the router; `npm run build` clean.
- **Depends-on:** T-196

### T-200 Shared Circuit JSON preview pane (both editors)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** A single `<CircuitPreviewPane circuitJson={…} />` component both the atopile editor (T-196) and the tscircuit-JSX editor mount. Reuses the `circuit-to-svg` rendering path already wired in `CircuitJsonPreview.jsx` (T-192). Visual parity = no UX confusion.
- **Target files/packages:** `src/components/CircuitPreviewPane.jsx` (NEW), `src/components/CircuitPreviewPane.test.jsx` (NEW vitest). TODO comments for parent integration into the two editor hosts.
- **Definition of Done:** the component renders identically for a Circuit JSON whether the source was atopile-compiled or tscircuit-emitted; pan/zoom works; vitest renders without errors; `npm run build` clean.
- **Depends-on:** T-192

### T-201 atopile → tscircuit JSX one-way converter
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Walk an atopile AST (T-194) and emit a `.tsx` source string usable in the tscircuit JSX editor. One-way only — reverse is intentionally NOT shipped (JSX side effects). Useful for "I prototyped visually, let me put it in version control as `.ato`" (wait — that's the wrong direction; the value is "I wrote it as `.ato` and want a quick visual sketch as `.tsx`"). Pure Python.
- **Target files/packages:** `packages/kerf-electronics/src/kerf_electronics/atopile/to_tscircuit.py` (NEW), `packages/kerf-electronics/tests/test_atopile_to_tscircuit.py` (NEW).
- **Definition of Done:** voltage_divider.ato → a `.tsx` source string that, when parsed by `@tscircuit/core` (or by our own validator), produces the same Circuit JSON as the atopile compiler does; pytest oracles against the 4 fixtures from T-194; `npm run build` clean.
- **Depends-on:** T-194, T-195

### T-202 Comparison page — "tscircuit vs atopile" personas
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** A `src/routes/compare/TscircuitVsAtopile.jsx` page that lays out the two authoring styles side-by-side. Two columns ("Visual-first" vs "Code-first"); same Circuit JSON example rendered as JSX on the left and `.ato` on the right; "Both produce KiCad" callout below. No "winner"; both are first-class. Add it to the existing compare-page registry (`src/routes/compare/index.jsx`) — additive only.
- **Target files/packages:** `src/routes/compare/TscircuitVsAtopile.jsx` (NEW), `src/routes/compare/TscircuitVsAtopile.test.jsx` (NEW vitest), append the route + nav entry in `src/routes/compare/index.jsx` (additive, do not delete existing entries).
- **Definition of Done:** the page renders at `/compare/tscircuit-vs-atopile`; both code examples are visible; "Both produce KiCad" callout present; vitest; `npm run build` clean.
- **Depends-on:** none

### T-203 Landing-page Electronics section — pair messaging
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** Surface BOTH authoring styles equally on the Electronics-section of `src/routes/Landing.jsx`. New tagline near the Electronics card: "Two authoring styles, one fabrication target." Mention atopile + tscircuit by name with file-extension hints. Add a small `public/docs/electronics-authoring.md` (or similar — check `public/docs-manifest.json` source) that explains the pair from the user's standpoint.
- **Target files/packages:** `src/routes/Landing.jsx` (additive — DO NOT remove existing sectors), `public/docs/electronics-authoring.md` (NEW; DO NOT commit `public/docs-manifest.json`), tests assert the tagline text appears in the Electronics card.
- **Definition of Done:** Landing's Electronics section names both authoring styles; doc renders in the in-app docs viewer; vitest; `npm run build` clean.
- **Depends-on:** none


## Render scene Blender-parity (T-204 … T-208) — sun, sky, clouds, gizmos

User reported 2026-05-18: adding a "Sun" light in the Render panel has zero visible effect at any angle. Root cause: `RenderView.jsx` writes `doc.lights[]` metadata but `Renderer.jsx` ignores it — it renders four hard-coded directional lights. The data layer + UI exist; the scene-graph application is missing. Wider goal: parity with Blender's sun + sky + cloud presets so the in-viewport look matches what the user picks.

### T-204 Wire `doc.lights[]` into the live Three.js scene (FIX)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** consume `doc.lights[]` from `src/lib/render.js` inside `src/components/Renderer.jsx`. Each entry becomes the corresponding `THREE.*Light`:
  - `sun` → `DirectionalLight` (use `direction[]` to set position from target); enable shadow casting when the light's `cast_shadow` flag is true.
  - `area` → `RectAreaLight` (needs `RectAreaLightUniformsLib.init()` once at scene setup).
  - `point` → `PointLight`.
  - `spot` → `SpotLight` (use `direction[]` for target).
  Add a small effect ref tracking the spawned lights so they're disposed and recreated when `doc.lights` changes. Preserve the existing hard-coded key/fill/bounce/rim as the **default rig** only when `doc.lights` is empty.
- **Target files/packages:** `src/components/Renderer.jsx` (additive — DO NOT remove the existing lights; gate them behind `doc.lights.length === 0`), `src/lib/applyDocLightsToScene.js` (NEW pure-logic helper), vitest.
- **Definition of Done:** adding a sun via the Render panel moves the highlight on the model when direction changes; switching `kind` between sun/area/point/spot updates the scene; vitest renders the helper without errors; `npm run build` clean.
- **Depends-on:** none

### T-205 Procedural sky + sun-position atmospheric scattering
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add a `<Sky>` background option using `three/examples/jsm/objects/Sky.js`. Two new doc-level settings: `sky.kind ∈ {none|procedural|hdri}` and `sky.sun_position {elevation_deg, azimuth_deg}`. When procedural, the sun light's direction syncs from `sky.sun_position` (one source of truth). Picker UI in the Render dropdown alongside the existing Daylight toggle.
- **Target files/packages:** `src/lib/sky.js` (NEW), `src/components/SkySettings.jsx` (NEW), additive into `src/components/Renderer.jsx` and `src/components/RenderView.jsx` (no deletion); vitest on the pure-logic.
- **Definition of Done:** changing sun elevation/azimuth animates the sky colour + sun-light direction together; vitest on the elevation→direction math; `npm run build` clean.
- **Depends-on:** T-204

### T-206 Volumetric / billboard cloud layer
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add an opt-in cloud layer to the procedural sky from T-205. Cloud "kinds": `none`, `scattered`, `overcast`, `storm`. Implementation can be billboard-quad-based (cheap; sample noise → opacity) — full volumetric is out of scope. Cloud opacity + density expose two sliders in `SkySettings`.
- **Target files/packages:** `src/lib/clouds.js` (NEW), `src/components/CloudLayer.jsx` (NEW — declarative Three.js cloud-quad component), vitest.
- **Definition of Done:** scattered clouds visible against the procedural sky; sliders update density without re-mounting; vitest on the noise sampler; `npm run build` clean.
- **Depends-on:** T-205

### T-207 HDRI sky preset library — clear / overcast / sunset / studio / night
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** curate 5 royalty-free 1-2K HDRIs (clear, overcast, sunset, studio, night) and wire them as one-click presets in `SkySettings.jsx` (T-205) under the `hdri` mode. Apply via the existing PMREM environment path. Each preset names its source/license inline.
- **Target files/packages:** `public/hdri/` (NEW assets), `src/lib/hdriPresets.js` (NEW), `src/components/HdriPicker.jsx` (NEW), small additive change in `Renderer.jsx` to swap the environment from the picker. Vitest for the pure-logic list.
- **Definition of Done:** picking each preset swaps the env map within ~1 s; PBR materials respond to each; vitest on the preset registry; `npm run build` clean.
- **Depends-on:** T-205

### T-208 In-viewport light gizmos (sun arrow, area rect, point sphere, spot cone)
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** render a small Three.js gizmo per `doc.lights[]` entry inside the viewport so the user SEES what they're editing. Sun → arrow + circle at the world origin; area → outlined rect; point → wire-sphere; spot → cone. Click-to-select binds the gizmo to the editing panel.
- **Target files/packages:** `src/components/LightGizmos.jsx` (NEW), additive into `Renderer.jsx`. Vitest on the pure-helpers that build gizmo geometry; gate the gizmo overlay behind a per-doc `show_gizmos` flag (default true).
- **Definition of Done:** each light type renders its correct gizmo at the right position/direction; clicking the gizmo highlights the corresponding entry in the Render panel list; vitest on gizmo-geometry helpers; `npm run build` clean.
- **Depends-on:** T-204


## Render variety — styles / post-fx / IES / cameras / studios (T-209 … T-213)

User-direction 2026-05-18: "look at Blender and other CADs, I want variety of rendering options and different lighting options." Survey across **Blender** (Eevee + Cycles), **KeyShot**, **Fusion 360** (in-canvas + Render), **SOLIDWORKS Visualize**, **Onshape**, **Rhino Cycles**. Five things every modern CAD/render tool ships that we don't:

### T-209 Render-style presets — Realistic / Cel / Wireframe / Hidden-line / Sketch / Blueprint
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** non-photorealistic render (NPR) modes. Six presets:
  1. **Realistic** — current PBR pipeline (default)
  2. **Cel-shaded** — quantised lambert + outline pass
  3. **Wireframe** — line-only, edges only
  4. **Hidden-line** — front-facing wireframe + dashed back lines (architectural cliché)
  5. **Sketch** — pencil/hand-drawn NPR using a screen-space hatching shader
  6. **Blueprint** — white-on-blue technical-drawing style with constant edge weights
  All implemented as post-processing passes (no per-mesh shader swap). Picker UI in the Render dropdown.
- **Target files/packages:** `src/lib/renderStyles.js` (NEW), `src/components/RenderStylePicker.jsx` (NEW), additive into `Renderer.jsx`; vitest on the style registry.
- **Definition of Done:** all six styles switchable live; current PBR is the default and looks identical to before; vitest; `npm run build` clean.
- **Depends-on:** none

### T-210 Post-effects stack — bloom, DoF, vignette, grain, SSAO, chromatic aberration
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** extend the current EffectComposer pipeline (bloom is shipped) with **depth-of-field** (Bokeh, focal-distance slider), **vignette** (corner-darkening), **film grain** (animated noise), **SSAO** (screen-space ambient occlusion — already in three-mesh-bvh ecosystem), and **chromatic aberration** (lens dispersion). Each effect toggleable; sliders for the salient parameter (DoF focal-distance + aperture; SSAO radius + intensity). One unified "Post" panel in the Render dropdown.
- **Target files/packages:** `src/lib/postEffects.js` (NEW), `src/components/PostEffectsPanel.jsx` (NEW), additive into `Renderer.jsx`; vitest on the pure-logic toggles and parameter clamping.
- **Definition of Done:** each effect can be toggled live; DoF focal-distance picker uses a small reticle in the viewport; vitest; `npm run build` clean.
- **Depends-on:** none

### T-211 IES light profiles library — architectural lighting realism
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** support **IES photometric profiles** (industry-standard `.ies` files). Add a "Photometric" light kind to `doc.lights[]` carrying an IES filename + intensity. Three.js has `IESLoader` from examples. Ship 12+ curated free profiles (covering downlight, wall-wash, batwing, narrow-spot, flood). Per-light picker UI with a small polar-plot preview.
- **Target files/packages:** `src/lib/iesLoader.js` (NEW — wrap three's IESLoader), `src/lib/iesPresets.js` (NEW — 12 profile catalogue), `public/ies/*.ies` (NEW assets), `src/components/IesProfilePicker.jsx` (NEW). Vitest on the preset catalogue + a polar-plot sampler.
- **Definition of Done:** assigning an IES profile to a point/spot light produces the characteristic photometric distribution; preset picker swaps profiles live; vitest; `npm run build` clean.
- **Depends-on:** T-204

### T-212 Camera lens variety — perspective, ortho, fisheye, two-point, panoramic 360
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** camera-projection switcher. Five modes:
  1. **Perspective** (current default)
  2. **Orthographic** (engineering / drawings)
  3. **Two-point perspective** (architectural — verticals stay vertical)
  4. **Fisheye** (`THREE.CubeCamera` + shader projection — 180°)
  5. **Panoramic 360** (full-sphere — for hero render only, slow)
  Plus a **focal-length slider** (mm) and **sensor size selector** (full-frame, APS-C, 35mm cinema) that drive the perspective FOV with photographer-friendly numbers.
- **Target files/packages:** `src/lib/cameraProjections.js` (NEW), `src/components/CameraLensPicker.jsx` (NEW), additive into `Renderer.jsx`. Vitest on the focal-length → FOV math (standard formula `FOV = 2·atan(sensor / (2·focal))`).
- **Definition of Done:** switching projection swaps the camera without losing the orbit target; focal-length slider produces the analytic FOV to 1e-6; vitest; `npm run build` clean.
- **Depends-on:** none

### T-213 Studio-lighting preset library — 3-point / 4-point / butterfly / Rembrandt / ring / softbox
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** one-click lighting rigs that populate `doc.lights[]` with a complete preset. Six presets:
  1. **Three-point** (key + fill + back) — already in `presetThreePointLighting` (kept)
  2. **Four-point** (key + fill + back + kicker)
  3. **Butterfly** (overhead key + low fill — beauty/portrait)
  4. **Rembrandt** (45° key + low fill — moody / sculpture)
  5. **Ring light** (single ring around the camera — jewelry / product)
  6. **Softbox** (large rect area light overhead, 45° — product / catalogue)
  Picker UI in the Render dropdown; each preset clears+repopulates `doc.lights`.
- **Target files/packages:** extend `src/lib/render.js` (additive — DO NOT touch `presetThreePointLighting`), `src/components/StudioLightingPicker.jsx` (NEW). Vitest on each preset's light count + position.
- **Definition of Done:** applying any preset visibly relights the scene (depends on T-204 wire-up); pickers swap presets cleanly; vitest oracles on light positions; `npm run build` clean.
- **Depends-on:** T-204


## Viewport polish (T-215 … T-219) — day-night, quality presets, material editor, keybinds, shadows

### T-215 Animated sun-driven day-night cycle UI
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add a "Time of day" slider that drives the sun position (T-205 sky + T-204 sun light) from sunrise → noon → sunset → night. Tweens elevation/azimuth + sun colour temperature + sky turbidity. Play/pause button for an animated cycle.
- **Target files/packages:** `src/lib/dayNightCycle.js` (NEW), `src/lib/dayNightCycle.test.js` (NEW), `src/components/DayNightSlider.jsx` (NEW), `src/components/DayNightSlider.test.jsx` (NEW)
- **Definition of Done:** slider position maps to (elevation, azimuth, K) deterministically; play mode animates without dropped frames; vitest oracles on the time→position math; `npm run build` clean.
- **Depends-on:** T-205

### T-216 Render quality presets (Draft / Preview / Final / Path-traced)
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** four one-click quality presets that batch-set: samples, max bounces, post-fx (T-210), shadow map size (T-219), AA mode. Maps cleanly between the in-viewport realtime path and the T-106b Cycles worker.
- **Target files/packages:** `src/lib/qualityPresets.js` (NEW), `src/lib/qualityPresets.test.js` (NEW), `src/components/QualityPicker.jsx` (NEW), `src/components/QualityPicker.test.jsx` (NEW)
- **Definition of Done:** each preset toggles the expected settings deterministically; vitest oracles; `npm run build` clean.
- **Depends-on:** none

### T-217 Material editor panel — live PBR slider preview
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** a side-panel material editor that exposes the full MeshPhysicalMaterial knob set (base_color, metalness, roughness, ior, transmission, clearcoat, sheen, anisotropy, subsurface) with sliders + live preview sphere. Loads a material from T-115 (BIM) or T-214 (general PBR) and lets the user fork+save.
- **Target files/packages:** `src/components/MaterialEditor.jsx` (NEW), `src/components/MaterialEditor.test.jsx` (NEW), `src/lib/materialPreviewSphere.js` (NEW), `src/lib/materialPreviewSphere.test.js` (NEW)
- **Definition of Done:** sliders update the preview sphere in real-time; "Save as…" creates a new material entry; vitest oracles on the slider→material math; `npm run build` clean.
- **Depends-on:** T-115 (already ✅)

### T-218 Viewport keybinds — Blender-style
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** keyboard shortcuts familiar to Blender / Maya users: `1/3/7` for front/right/top views, `Numpad 0` for camera view, `G/R/S` for transform modes (translate/rotate/scale), `Z` for wireframe toggle, `Shift+Z` for rendered/material view, `T` for transform gizmo toggle, `~` for view-pie-menu. Configurable via a JSON file.
- **Target files/packages:** `src/lib/viewportKeybinds.js` (NEW), `src/lib/viewportKeybinds.test.js` (NEW), `src/components/KeybindHelp.jsx` (NEW), `src/components/KeybindHelp.test.jsx` (NEW)
- **Definition of Done:** each keybind dispatches an event the renderer can listen for; vitest fires KeyboardEvent and asserts the right action emitted; `npm run build` clean.
- **Depends-on:** none

### T-219 Shadow controls — PCF / VSM / raytraced + shadow map size
- **Tier:** B
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** expose Three.js shadow knobs: shadow-map type (BasicShadowMap / PCFShadowMap / PCFSoftShadowMap / VSMShadowMap), per-light `castShadow` toggle, shadow map size selector (512 / 1024 / 2048 / 4096), shadow bias slider. UI in the Render dropdown alongside Daylight + Exposure.
- **Target files/packages:** `src/lib/shadowSettings.js` (NEW), `src/lib/shadowSettings.test.js` (NEW), `src/components/ShadowSettings.jsx` (NEW), `src/components/ShadowSettings.test.jsx` (NEW)
- **Definition of Done:** changing shadow-map type re-issues the renderer; vitest oracles on the enum mapping (PCF → THREE.PCFShadowMap); `npm run build` clean.
- **Depends-on:** T-204


## PLC textual + visual + simulator (T-220 … T-224)

User-direction 2026-05-18: "look at open-source ladder logic with nice UI/UX, standard file type, compile + simulate it along with the other textual PLC file." We already ship `kerf-plc` with `ld/` (ladder schema/renderer/export/lint via MATIEC). Build the visual editor, standardise on **PLCopen XML** (IEC TR 61131-10) as the file format, add a textual **IL (Instruction List)** + **ST (Structured Text)** path, and a pure-Python **scan-cycle simulator** + **HMI test panel** so users can wire inputs/outputs and watch state.

### T-220 PLCopen XML reader/writer — canonical IEC 61131-3 file format
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python reader/writer for **PLCopen XML** (the IEC standard interchange format used by Beremiz, Codesys, OpenPLC). Each `.plc` project is a PLCopen XML doc containing one or more **POU**s (Program Organization Units) in **LD**, **ST**, **FBD**, or **IL** form. The reader produces a Python AST (dataclasses); the writer round-trips. Standardise on `.plc` extension for the whole project and `.iec` for single POUs. Folder kind: `plc` (already in files_kind_check union as `plc_ld` + `plc_st` — keep both but treat a `.plc` file as a `plc_project` kind).
- **Target files/packages:** `packages/kerf-plc/src/kerf_plc/plcopen/__init__.py` (NEW), `packages/kerf-plc/src/kerf_plc/plcopen/reader.py` (NEW), `packages/kerf-plc/src/kerf_plc/plcopen/writer.py` (NEW), `packages/kerf-plc/src/kerf_plc/plcopen/ast.py` (NEW), `packages/kerf-plc/tests/test_plcopen.py` (NEW), `packages/kerf-plc/tests/fixtures/blinker.plc` (NEW), `packages/kerf-plc/tests/fixtures/conveyor.plc` (NEW).
- **Definition of Done:** Beremiz / OpenPLC's own example projects (`blinker.xml`, `traffic-light.xml`) round-trip byte-stable; pytest oracles on POU/Variable/Rung/Contact counts; `npm run build` clean.
- **Depends-on:** none

### T-221 Ladder visual editor — SVG canvas + drag-place contacts/coils
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** web-based ladder diagram (LD) editor: SVG canvas, left+right rails, rungs added on click, drag-place: normally-open contact, normally-closed contact, output coil, set/reset coil, rising-edge contact, function-block (TON timer, CTU counter). Right-click to delete; left-click on a contact opens an inline name editor. Round-trips through the T-220 PLCopen XML reader/writer. Reuses existing `kerf-plc/ld/renderer.py` and `schema.py` where possible.
- **Target files/packages:** `src/components/LadderEditor.jsx` (NEW), `src/components/LadderEditor.test.jsx` (NEW), `src/lib/ladderCanvas.js` (NEW pure-logic — rung/contact placement + collision math), `src/lib/ladderCanvas.test.js` (NEW vitest).
- **Definition of Done:** drag any contact/coil onto the canvas, edit its variable name, save → PLCopen XML round-trips clean; right-click delete works; vitest on the placement-collision math; `npm run build` clean.
- **Depends-on:** T-220

### T-222 Structured Text (ST) parser + editor support
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python ST parser per IEC 61131-3: VAR/VAR_INPUT/VAR_OUTPUT declarations, IF/THEN/ELSE, FOR/WHILE/REPEAT loops, CASE statements, function calls, expressions with the IEC type system (BOOL, INT, REAL, TIME, …). Monaco editor mode for `.st` and ST POUs inside a `.plc` PLCopen project. AST round-trips through T-220's writer.
- **Target files/packages:** `packages/kerf-plc/src/kerf_plc/st/__init__.py` (NEW), `packages/kerf-plc/src/kerf_plc/st/parser.py` (NEW), `packages/kerf-plc/src/kerf_plc/st/ast.py` (NEW), `packages/kerf-plc/src/kerf_plc/st/lexer.py` (NEW), `packages/kerf-plc/tests/test_st_parser.py` (NEW), `src/lib/stMonacoLanguage.js` (NEW frontend Monaco mode), `src/lib/stMonacoLanguage.test.js` (NEW).
- **Definition of Done:** the OpenPLC stock `blinker.st` parses to a non-empty AST; round-trip via T-220's writer preserves variable order + statement count; Monaco tokens cover the IEC 61131-3 reserved-word set; pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-220

### T-223 IEC 61131-3 scan-cycle simulator (LD + ST)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python scan-cycle simulator. One **tick** = (1) read inputs, (2) execute POU(s) — ladder rungs left→right or ST statements top→down, (3) write outputs. Default tick = 1 ms. Supports the standard function blocks: **TON** (on-delay timer), **TOF** (off-delay timer), **CTU/CTD** (up/down counter), **R_TRIG/F_TRIG** (rising/falling edge), **RS/SR** (set-reset flip-flop). Inputs/outputs are externally injectable; the simulator publishes a state-trace per tick.
- **Target files/packages:** `packages/kerf-plc/src/kerf_plc/simulator/__init__.py` (NEW), `packages/kerf-plc/src/kerf_plc/simulator/scan.py` (NEW), `packages/kerf-plc/src/kerf_plc/simulator/function_blocks.py` (NEW), `packages/kerf-plc/src/kerf_plc/simulator/state.py` (NEW), `packages/kerf-plc/tests/test_simulator.py` (NEW).
- **Definition of Done:** blinker.plc (TON-driven 1 Hz square wave) runs 5 s of simulated time → exact pulse count = 10; CTU counts edges correctly; F_TRIG fires once per falling edge; pytest analytic oracles; `npm run build` clean.
- **Depends-on:** T-220

### T-224 PLC HMI tester panel — inputs / outputs / state-trace timeline
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** React side-panel that runs a loaded `.plc` project against the T-223 simulator: input rows with toggle / momentary-button / numeric-spinner; output rows with lamps + numeric readouts; play/pause/step buttons; a time-series chart of inputs/outputs over the last N ticks. One-click loadbacking of `blinker.plc` and `conveyor.plc` fixtures from T-220.
- **Target files/packages:** `src/components/PlcHmiTester.jsx` (NEW), `src/components/PlcHmiTester.test.jsx` (NEW), `src/lib/plcSimBridge.js` (NEW — fetch wrapper around a `/plc/sim/step` backend route), `src/lib/plcSimBridge.test.js` (NEW), `packages/kerf-api/src/kerf_api/routes_plc_sim.py` (NEW HTTP route around T-223), `packages/kerf-api/tests/test_routes_plc_sim.py` (NEW).
- **Definition of Done:** loading blinker.plc → output coil pulses on the trace at the expected period; toggling an input flips outputs deterministically; pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-220, T-221, T-223

## Firmware — direct-gcc orchestrator + library registry (T-225 … T-230)

User-direction 2026-05-18: the existing `kerf-firmware` (T-130) is a thin `pio` subprocess wrapper; rebuild it as a **direct-gcc orchestrator** that subprocesses the cross-compilers (`avr-gcc`, `arm-none-eabi-gcc`, `xtensa-esp32-gcc`, `riscv-none-elf-gcc`) and talks to PlatformIO's library registry + Arduino's `library_index.json` over HTTP. **Do NOT** subprocess `pio`. Same operational pattern as CalculiX/Z88/Mystran bridges. The win: JSON-everywhere (`kerf.fw.json` replaces `platformio.ini`), no dependency on a third-party CLI for the build, the LLM owns a single schema family. See ROADMAP §3.5a. The PCB-design layer already ships in `kerf-electronics`; firmware closes the loop — one project authors the schematic, routes the board, generates Gerbers, **and** writes the firmware that runs on the MCU it just designed.

### T-225 Board catalogue + library-registry HTTP client (no pio subprocess)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python (1) board catalogue JSON mirroring ~200 popular boards across the AVR / ARM Cortex-M / ESP32 (xtensa + RISC-V) / RP2040 / SAMD / nRF52 families — each entry has `id`, `mcu`, `arch`, `f_cpu`, `flash`, `ram`, `core` (arduino/mbed/zephyr/none), `upload_protocol`, `upload_tool`, `pin_map` (Arduino-pin → MCU pin). Source = PlatformIO `boards.json` schema converted once at seed-time, then committed as a vendored mirror so we never need PlatformIO at runtime. (2) HTTP client against `https://api.registry.platformio.org/v3/libraries?query=…` and `https://downloads.arduino.cc/libraries/library_index.json` with httpx + on-disk JSON cache keyed by `(registry, query)`. NO `subprocess pio` anywhere. Targeted boards covered in v1: UNO R3, Nano (ATmega328P), Mega 2560, Pro Micro (ATmega32U4), Teensy 4.0/4.1, BluePill (STM32F103), Nucleo F411, ESP8266 NodeMCU, ESP32 DevKitC, ESP32-S3, ESP32-C3 (RISC-V), RP2040 Pico, RP2040 Pico W, ATtiny85, SAMD21 (Arduino Zero), nRF52840 (Adafruit Feather), Wemos D1 Mini.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/catalogue/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/catalogue/boards.json` (NEW vendored mirror, ~200 boards), `packages/kerf-firmware/src/kerf_firmware/catalogue/load.py` (NEW — load + validate against a dataclass schema), `packages/kerf-firmware/src/kerf_firmware/registry/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/registry/platformio.py` (NEW — v3 search + library detail), `packages/kerf-firmware/src/kerf_firmware/registry/arduino.py` (NEW — library_index.json reader), `packages/kerf-firmware/src/kerf_firmware/registry/cache.py` (NEW — keyed on-disk JSON cache), `packages/kerf-firmware/tests/test_catalogue.py` (NEW), `packages/kerf-firmware/tests/test_registry.py` (NEW — uses respx to mock HTTP).
- **Definition of Done:** `kerf_firmware.catalogue.load_boards()` returns >= 200 boards; ESP32 DevKitC entry has `arch="xtensa"`, `core="arduino"`, `upload_tool="esptool"`; PlatformIO v3 search for `"FastLED"` (mocked) returns hits with `name`/`version`/`repository.url`; Arduino library_index search for `"Adafruit_NeoPixel"` (mocked) returns hits; cache key collision returns the cached response without an HTTP call (assert via respx call-count); `pio`/`platformio` binaries are never invoked (grep test); `npm run build` clean.
- **Depends-on:** none

### T-226 `library.json` / `library.properties` parser + content-addressed library cache
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python parsers for the two library manifest formats: PlatformIO's `library.json` (JSON, well-specified) and Arduino's `library.properties` (key=value, UTF-8). Both normalise to a single `Library` dataclass with `{name, version, author, license, repository, frameworks, platforms, dependencies[], includes[], sources[]}`. Followed by a **content-addressed library cache**: clone-on-demand from `repository.url` into `~/.kerf/firmware-libs/<sha256>/` keyed on the git-tree-SHA at the requested version — same dedup pattern as the Git LFS substrate so two user projects pinning identical `FastLED 3.6.0` share one on-disk copy. Cache lookup is content-hash, not name+version, so a fork resolving to the identical tree dedups against upstream.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/manifest/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/manifest/library_json.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/manifest/library_properties.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/manifest/normalise.py` (NEW — produces the unified `Library` dataclass), `packages/kerf-firmware/src/kerf_firmware/libcache/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/libcache/store.py` (NEW — content-addressed `~/.kerf/firmware-libs/<sha256>/`), `packages/kerf-firmware/src/kerf_firmware/libcache/resolve.py` (NEW), `packages/kerf-firmware/tests/test_manifest.py` (NEW), `packages/kerf-firmware/tests/test_libcache.py` (NEW), `packages/kerf-firmware/tests/fixtures/library_json/` + `library_properties/` (NEW — 5 real-world fixtures each: FastLED, ArduinoJson, AsyncTCP, Adafruit_NeoPixel, U8g2).
- **Definition of Done:** `library.json` and `library.properties` for all 10 fixtures parse to a `Library` with `name`, `version`, `dependencies` non-empty where expected; normalise to the unified shape (Arduino `depends` and PlatformIO `dependencies` both land in `Library.dependencies[]`); cache resolves `FastLED@3.6.0` twice → exactly one git-clone subprocess (assert call-count); dedup test: two `Library` entries with identical resolved tree-SHAs share the on-disk path; pytest oracles; `npm run build` clean.
- **Depends-on:** T-225

### T-227 Direct-gcc build orchestrator (avr / arm-none-eabi / xtensa / riscv)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** pure-Python build orchestrator that takes a `kerf.fw.json` project + a resolved board + a set of resolved libraries (T-225 + T-226) and invokes the **architecture cross-compiler directly**, producing `.elf` / `.hex` / `.bin` artefacts in `<project>/.kerf-fw/build/<env>/`. One profile per arch, each subprocessing the stock gcc toolchain: `avr-gcc` / `avr-g++` / `avr-ld` / `avr-objcopy` (AVR); `arm-none-eabi-gcc` / `arm-none-eabi-g++` / `arm-none-eabi-ld` / `arm-none-eabi-objcopy` (Cortex-M); `xtensa-esp32-elf-gcc` (ESP32 xtensa); `riscv-none-elf-gcc` (RP2040 dual-core M0+ is ARM; this is for ESP32-C3/S2 RISC-V variants). Build steps: collect sources from project + each resolved library; compile each to `.o` with the correct `-mmcu` / `-mcpu` / `-march` flags (looked up by board.arch in T-225); link with the board's vendor linker script when present (`.ld` files are part of the board catalogue payload); objcopy to `.hex`/`.bin`. Each toolchain is detected with the same `shutil.which()` pattern as CalculiX/Z88/Mystran; missing toolchain → sentinel + install hint (`brew install avr-gcc`, etc.); does **not** install toolchains for the user. Cloud workers get the toolchains pre-baked into the Docker image (separate from this task — covered in a deferred deploy task).
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/orchestrator/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/profiles/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/profiles/avr.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/profiles/arm_none_eabi.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/profiles/xtensa.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/profiles/riscv.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/orchestrator/compile_link.py` (NEW — shared gcc/g++/ld/objcopy subprocess plumbing), `packages/kerf-firmware/src/kerf_firmware/orchestrator/sentinel.py` (NEW — missing-toolchain hint), `packages/kerf-firmware/tests/test_orchestrator.py` (NEW), `packages/kerf-firmware/tests/fixtures/blink_uno/` (NEW — minimal Blink fixture), `packages/kerf-firmware/tests/fixtures/blink_esp32/` (NEW), `packages/kerf-firmware/tests/fixtures/blink_bluepill/` (NEW).
- **Definition of Done:** when `avr-gcc` is on `$PATH`, building `blink_uno/main.ino` produces a `firmware.hex` whose section sizes parse > 0; when `avr-gcc` is absent the orchestrator returns the install-hint sentinel and never raises; same matrix for arm-none-eabi against `blink_bluepill/` and xtensa against `blink_esp32/`; gcc command lines include the expected `-mmcu=atmega328p` (AVR) / `-mcpu=cortex-m3` (BluePill) / equivalent for ESP32; the orchestrator never imports or shells out to `pio`/`platformio`; pytest with subprocess mocking + at least one real-toolchain integration test gated on toolchain presence; `npm run build` clean.
- **Depends-on:** T-225, T-226

### T-228 Upload wrappers — avrdude / esptool / stm32flash / bossac (CLI-only)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** thin subprocess wrappers for the four standard upload tools — `avrdude` (AVR), `esptool.py` (ESP8266/ESP32), `stm32flash` (STM32 over UART), `bossac` (SAMD / Atmel). Each accepts a built artefact (`.hex`/`.bin`) + a serial port and returns `{ok, log, bytes_written}`. **Cloud path:** when the request comes via the hosted API, the response is the install-hint sentinel — flashing a board requires physical USB, which only the local Kerf CLI has. **Local CLI path:** the wrappers are invoked, port detection uses pyserial's `list_ports`, results stream back. Upload tool is chosen by `board.upload_tool` from the T-225 catalogue. Auto-port-detection picks the first port whose VID/PID matches the board (where known; fallback = first non-system port + user prompt).
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/upload/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/upload/avrdude.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/upload/esptool.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/upload/stm32flash.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/upload/bossac.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/upload/port_detect.py` (NEW — pyserial VID/PID match), `packages/kerf-firmware/tests/test_upload.py` (NEW — subprocess mocked + a real avrdude integration test gated on tool presence), `packages/kerf-cli/src/kerf_cli/commands/firmware_upload.py` (NEW — local-CLI command surface).
- **Definition of Done:** with mocked subprocess, each wrapper builds the correct argv (`avrdude -c arduino -p atmega328p -P /dev/ttyACM0 -U flash:w:firmware.hex:i`, `esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash 0x10000 firmware.bin`, `stm32flash -w firmware.bin -v /dev/ttyUSB0`, `bossac -i -d --port /dev/ttyACM0 -w -v firmware.bin -R`); cloud API path returns the sentinel + actionable install-hint without attempting upload; CLI path invokes the real tool when present; pytest oracles; `npm run build` clean.
- **Depends-on:** T-227

### T-229 Serial monitor — pyserial (CLI) + WebSerial (browser)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** dual-path serial monitor. **CLI:** `kerf firmware monitor <port> --baud 115200` uses pyserial to read bytes from the port and write them to stdout, with line-ending normalisation (`CR`/`LF`/`CRLF`/`raw`) and an opt-in timestamp prefix. **Browser:** `SerialMonitorPanel.jsx` uses the **WebSerial API** (`navigator.serial.requestPort()` then `port.readable.getReader()`) when supported by the browser; on browsers without WebSerial (Safari, Firefox today), the panel shows an "install Kerf CLI to monitor" hint that links to the CLI command. The panel offers baud-rate selection (300/1200/9600/19200/38400/57600/115200/230400), line-ending mode, send-line input, autoscroll toggle, and a downloadable `serial.log` of the captured session.
- **Target files/packages:** `packages/kerf-cli/src/kerf_cli/commands/firmware_monitor.py` (NEW — pyserial loop), `packages/kerf-cli/tests/test_firmware_monitor.py` (NEW — pyserial mocked), `src/components/SerialMonitorPanel.jsx` (NEW), `src/components/SerialMonitorPanel.test.jsx` (NEW — vitest with WebSerial mocked), `src/lib/webSerialBridge.js` (NEW — wraps `navigator.serial.*` with a clean Promise interface).
- **Definition of Done:** CLI: when pyserial yields a sequence of bytes the command prints them in the configured line-ending; Browser: when WebSerial is mocked-available, the panel calls `requestPort()` on user gesture, reads the mocked stream, and renders lines; when WebSerial is mocked-absent, the panel shows the CLI install-hint and never throws; baud-rate change reopens the port (vitest assertion); pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-225

### T-230 LLM tool `make_arduino_sketch(spec)` + `kerf.fw.json` project manifest schema
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** the LLM-facing surface for the new firmware track. (1) Define `kerf.fw.json` — a JSON project manifest with `{ board, framework, sources[], libraries[{name, version}], upload: {port?, baud?}, monitor: {baud?, line_ending?} }`, schema published in `packages/kerf-firmware/llm_docs/firmware.md`. Interconvertible with `platformio.ini` via a one-way `kerf fw import-pio platformio.ini` converter for migration. (2) `make_arduino_sketch(spec)` LLM tool that takes a natural-language spec (`"blink an LED on pin 13 at 1 Hz on an Arduino UNO"`) + an optional pin map, emits `main.ino` + a `kerf.fw.json`, resolves library dependencies via T-226, and (when toolchain is present) compiles via T-227 returning the artefact paths. (3) Sister tool `lint_arduino_sketch(path)` runs a fast syntactic check via the gcc preprocessor in `-E` mode without linking (catches missing headers / typos before a full build). (4) Add file kinds `firmware_project` (for `.fw.json` / `kerf.fw.json`) — `firmware` already exists in `files_kind_check`; the `.ino` / `.uno` / `.c` / `.cpp` / `.h` files keep `kind='file'` and use the T-116 text-highlight path.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/manifest_fw_json.py` (NEW — `kerf.fw.json` schema + validator), `packages/kerf-firmware/src/kerf_firmware/tools/make_sketch.py` (NEW — LLM tool), `packages/kerf-firmware/src/kerf_firmware/tools/lint_sketch.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/tools/import_pio.py` (NEW — one-way `platformio.ini` → `kerf.fw.json` converter), `packages/kerf-firmware/llm_docs/firmware.md` (NEW — schema + tool usage), `packages/kerf-firmware/tests/test_manifest_fw_json.py` (NEW), `packages/kerf-firmware/tests/test_make_sketch.py` (NEW), `packages/kerf-firmware/tests/test_import_pio.py` (NEW — round-trip on Blink, BluePill, ESP32 sample `platformio.ini`).
- **Definition of Done:** `make_arduino_sketch("blink an LED on pin 13 at 1 Hz on an Arduino UNO")` emits a valid `kerf.fw.json` + a `main.ino` that compiles with `avr-gcc` (when present; sentinel when absent); `lint_arduino_sketch` flags a missing-header source as `errored=true` with a clear gcc-preprocessor message; import: a 10-line `platformio.ini` converts to a `kerf.fw.json` whose `board`+`framework`+`libraries` match by string equality; `llm_docs/firmware.md` linted by the existing doc-manifest builder; pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-226, T-227

## Silicon / EDA / VHDL — open-source full-flow chip design (T-231 … T-248)

**Strategic frame** (ROADMAP §3.5b): ~80% of the silicon-design flow is now open source — GHDL (VHDL), Verilator + Icarus (Verilog), Yosys (synthesis), OpenROAD + OpenLane (place-and-route + GDS-II, **tape-out-proven on 600+ chips**), Skywater SKY130 + GF180MCU + IHP SG13G2 (open PDKs), ngspice + Xyce (SPICE), KLayout (GDS-II + OASIS viewer/editor). No one has assembled it into a **cloud-native, AI-native, browser-accessible** tool. We do. Three phases: **Phase 1 (T-231..T-236)** = RTL front-end (HDL parsing + behavioural simulation + Yosys/GHDL bridges + ngspice mixed-signal); **Phase 2 (T-237..T-242)** = layout back-end (GDS-II, KLayout-shape viewer, PDK integration, LEF/DEF, Liberty, OpenROAD/OpenLane RTL→GDS-II); **Phase 3 (T-243..T-248)** = verification + characterisation (schematic-to-mask, DRC, LVS, parasitic extraction, mask generation, node characterisation). File kinds + extensions land in a deferred migration (T-248). New package: `packages/kerf-silicon/`.

### T-231 VHDL lexer/parser — pure Python, IEEE 1076-2008 subset
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** pure-Python lexer + parser for the subset of IEEE 1076 VHDL needed for behavioural and synthesizable RTL: entity, architecture, port maps, signals/variables/constants, generics, `process` blocks with sensitivity lists, sequential statements (`if`/`case`/`for`/`while`/`wait`), concurrent statements, packages + `use` clauses, libraries (`std`, `ieee.std_logic_1164`, `ieee.numeric_std`). Types: `bit`, `bit_vector`, `std_logic`, `std_logic_vector`, `signed`, `unsigned`, `integer`, `boolean`, arrays, records, subtypes. AST is a tree of `@dataclass(frozen=True)` nodes with source-position metadata. Round-trips byte-stable on a 100-line canonical pretty-printer. Out-of-scope (future): protected types, full IEEE 1076-2019 generics, configuration declarations.
- **Target files/packages:** `packages/kerf-silicon/pyproject.toml` (NEW), `packages/kerf-silicon/src/kerf_silicon/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/lexer.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/parser.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/ast.py` (NEW — frozen dataclasses), `packages/kerf-silicon/src/kerf_silicon/vhdl/pretty.py` (NEW — pretty-printer), `packages/kerf-silicon/tests/test_vhdl_lexer.py` (NEW), `packages/kerf-silicon/tests/test_vhdl_parser.py` (NEW), `packages/kerf-silicon/tests/fixtures/vhdl/` (NEW — 12 fixtures: half-adder, full-adder, ripple-carry adder, 4-bit counter, FSM (Mealy + Moore), shift register, ALU, UART rx, UART tx, FIFO, blinker, GHDL test-bench skeleton).
- **Definition of Done:** all 12 fixtures lex without errors; all 12 parse to a non-empty AST; pretty-print → re-parse round-trips with AST equality; entity/architecture/process counts match the oracles per fixture; pytest analytic oracles; `npm run build` clean.
- **Depends-on:** none

### T-232 Verilog / SystemVerilog lexer/parser — pure Python, synthesizable subset
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** companion to T-231 for Verilog (IEEE 1364) and a SystemVerilog (IEEE 1800) subset. Covers `module` / `endmodule` / port lists / parameters, `wire`/`reg`/`logic` declarations, `assign`, `always_ff`/`always_comb`/`always_latch`, `case`/`casex`/`casez`, `for`/`while`/`repeat`/`forever`, `function`/`task`, packed + unpacked arrays, blocking vs non-blocking assignment, hierarchical references. SystemVerilog adds: `logic` type, packed structs/unions, enums, `typedef`, `interface` (parsed, not elaborated). AST is the same frozen-dataclass shape as T-231 so downstream consumers can dispatch on language. Out-of-scope (future): full constraint-randomization, classes/OOP, UVM, assertions (SVA).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/verilog/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/verilog/lexer.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/verilog/parser.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/verilog/ast.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/verilog/pretty.py` (NEW), `packages/kerf-silicon/tests/test_verilog_lexer.py` (NEW), `packages/kerf-silicon/tests/test_verilog_parser.py` (NEW), `packages/kerf-silicon/tests/fixtures/verilog/` (NEW — 12 fixtures mirroring T-231's set in both `.v` and `.sv` flavours where the SV one exercises `logic`/`enum`/`typedef`).
- **Definition of Done:** all 24 fixtures (12 `.v` + 12 `.sv`) parse to non-empty ASTs; pretty-print → re-parse round-trips with AST equality; `always_ff` vs `always_comb` correctly distinguished on the SV variant; pytest oracles; `npm run build` clean.
- **Depends-on:** none

### T-233 Behavioural VHDL simulator — event-driven, delta cycles, pure Python
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** pure-Python **event-driven simulator** with **delta-cycle** semantics over the T-231 AST. Maintains a sorted event queue keyed on `(time_fs, delta_count)`; on each delta, drives signals, fires every process whose sensitivity-list signal changed, schedules signal updates for the next delta, advances time only when the delta queue drains. Implements IEEE 1164 `std_logic` (9-state: `U X 0 1 Z W L H -`) with resolution-function semantics on multi-driven nets. Wait statements: `wait for <time>`, `wait on <signal>`, `wait until <expr>`, `wait` (forever). Default tick = 1 ps. VCD output for waveform viewing. Scope: educational / small designs — not a Verilator competitor; correctness > speed. The GHDL bridge (T-235) is the production path when designs outgrow this.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/vhdl/simulator/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/simulator/scheduler.py` (NEW — event queue + delta cycles), `packages/kerf-silicon/src/kerf_silicon/vhdl/simulator/std_logic.py` (NEW — 9-state resolution), `packages/kerf-silicon/src/kerf_silicon/vhdl/simulator/evaluator.py` (NEW — AST walker), `packages/kerf-silicon/src/kerf_silicon/vhdl/simulator/vcd.py` (NEW — VCD writer), `packages/kerf-silicon/tests/test_vhdl_simulator.py` (NEW).
- **Definition of Done:** running the half-adder fixture 100 ns produces the expected sum/carry trace at each input combination; the 4-bit counter rolls 0→15→0 over 16 clock edges; the Moore FSM transitions through its states in the expected order; `std_logic` resolution: driving `0`+`1` on the same net resolves to `X`; VCD output loads in `gtkwave` (manual verification) and re-parses to the same waveform; pytest analytic oracles; `npm run build` clean.
- **Depends-on:** T-231

### T-234 Yosys synthesis subprocess bridge (RTL → gate-level netlist)
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** subprocess wrapper around **Yosys** (ISC-licensed) — RTL → gate-level netlist. Takes a list of `.v` / `.sv` / `.vhd` files (VHDL via Yosys's `ghdl` plugin when present, fallback = T-235 GHDL bridge to synthesise `--synth` netlists first), a top module name, and a target library (`generic` / `cmos` / `sky130_fd_sc_hd`). Emits a JSON netlist (Yosys's native `write_json`), a structural Verilog gate-level netlist, and a gate-count / cell-area summary. Generates a Yosys script (`.ys`) per invocation, runs `yosys -s <script>`, captures stdout/stderr to a structured log. Missing-binary path returns sentinel + install hint (`brew install yosys`).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/synth/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/synth/yosys.py` (NEW — subprocess + script generator), `packages/kerf-silicon/src/kerf_silicon/synth/netlist_json.py` (NEW — parse Yosys's `write_json` output into a dataclass tree), `packages/kerf-silicon/tests/test_yosys_synth.py` (NEW — subprocess mocked + a yosys integration test gated on tool presence), `packages/kerf-silicon/tests/fixtures/synth/half_adder.v` (NEW), `packages/kerf-silicon/tests/fixtures/synth/counter4.v` (NEW), `packages/kerf-silicon/tests/fixtures/synth/half_adder_expected_netlist.json` (NEW — golden snapshot).
- **Definition of Done:** with mocked subprocess, the generated Yosys script contains `read_verilog`, `synth -top half_adder`, `write_json`, `write_verilog`; with real Yosys on `$PATH` (integration test gated on `shutil.which("yosys")`), the half-adder netlist contains exactly 2 cells (XOR + AND for `generic` lib); missing-yosys returns sentinel + install hint; pytest oracles; `npm run build` clean.
- **Depends-on:** T-232 (Verilog parser used to validate inputs before invoking yosys)

### T-235 GHDL VHDL simulator subprocess bridge
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** subprocess wrapper around **GHDL v6.x** (the GCC/LLVM-backed VHDL simulator). Takes a `.vhd` test-bench + design under test, runs `ghdl -a` (analyse), `ghdl -e` (elaborate), `ghdl -r` (run) with `--vcd=<out>` and `--stop-time=<time>`. Parses GHDL's compile-error format into structured `{file, line, severity, message}` records. Missing-binary path returns sentinel + install hint (`apt install ghdl` / `brew install ghdl`).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/vhdl/ghdl_bridge.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/vhdl/ghdl_errors.py` (NEW — error parser), `packages/kerf-silicon/tests/test_ghdl_bridge.py` (NEW — subprocess mocked + a real-ghdl integration test gated on tool presence), `packages/kerf-silicon/tests/fixtures/vhdl_sim/counter4_tb.vhd` (NEW), `packages/kerf-silicon/tests/fixtures/vhdl_sim/expected_counter4.vcd` (NEW — golden VCD).
- **Definition of Done:** with mocked subprocess, the wrapper invokes `ghdl -a`/`-e`/`-r` in order with the correct flags; with real GHDL on `$PATH`, the counter4 test-bench produces a VCD whose value-changes match the golden snapshot byte-for-byte (modulo timestamp); compile-error parser extracts at least 5 fields from a known-bad fixture; missing-ghdl returns sentinel; pytest oracles; `npm run build` clean.
- **Depends-on:** T-231

### T-236 ngspice mixed-signal extension — device-level SPICE for silicon
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** extend the existing `kerf-electronics` ngspice integration to handle device-level SPICE netlists for silicon (MOSFET-level, BSIM4 models, sub-circuits, parasitic networks). The existing `routes_spice.py` runs ngspice on PCB-level circuits; this task adds (1) a `.spice` / `.cir` file kind for raw netlists, (2) a transient/AC/DC/noise sweep wrapper that emits standard analysis types, (3) reads device models from a PDK directory (`sky130A.lib.spice` etc.) when the PDK is available (T-239), (4) plots the result via the existing wave-trace UI used for ngspice on PCB. Bridges T-231..T-235 (digital RTL) to T-243+ (mixed-signal verification).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/spice/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/spice/ngspice_bridge.py` (NEW — re-uses `kerf_electronics.routes_spice` patterns), `packages/kerf-silicon/src/kerf_silicon/spice/analyses.py` (NEW — transient / AC / DC / noise), `packages/kerf-silicon/src/kerf_silicon/spice/pdk_models.py` (NEW — read device-model `.spice` files from a PDK dir), `packages/kerf-silicon/tests/test_spice_silicon.py` (NEW), `packages/kerf-silicon/tests/fixtures/spice/inverter_sky130.cir` (NEW — CMOS inverter on SKY130 models).
- **Definition of Done:** with mocked ngspice, the inverter `.cir` runs through `tran 1n 100n` and the wrapper emits a structured `{time[], vout[]}` result; with real ngspice + SKY130 PDK models present (integration test gated), the inverter transitions cleanly with rise time < 1 ns; pytest oracles; `npm run build` clean.
- **Depends-on:** T-232

### T-237 GDS-II reader/writer — pure Python, KLayout-shape data model
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** pure-Python reader/writer for **GDS-II** — the standard binary IC-layout interchange format. Spec is well-documented (Cadence GDS-II Stream Format spec, public). Implements the record-by-record stream format: HEADER, BGNLIB, LIBNAME, UNITS, BGNSTR, STRNAME, BOUNDARY, PATH, SREF, AREF, TEXT, LAYER, DATATYPE, XY, ENDEL, ENDSTR, ENDLIB. Data model mirrors KLayout's `Cell` / `Shape` / `Polygon` / `Path` / `Text` / `Box` so we can interoperate with KLayout-the-tool when present without depending on it at runtime. Pure Python; no `klayout` package dependency.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/layout/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/gds/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/gds/reader.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/gds/writer.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/gds/records.py` (NEW — record-tag constants + struct layouts), `packages/kerf-silicon/src/kerf_silicon/layout/shapes.py` (NEW — `Cell` / `Polygon` / `Path` / `Text` / `Box` dataclasses, KLayout-shape parity), `packages/kerf-silicon/tests/test_gds_io.py` (NEW), `packages/kerf-silicon/tests/fixtures/gds/inverter_sky130.gds` (NEW — small KLayout-exported sample), `packages/kerf-silicon/tests/fixtures/gds/and2_sky130.gds` (NEW).
- **Definition of Done:** the SKY130 inverter `.gds` round-trips byte-stable through reader→writer (modulo trailing pad bytes that GDS-II tolerates); cell/polygon/layer counts match KLayout's reported counts on the same files; a 1000-polygon synthetic fixture round-trips in < 1 s; pytest oracles; `npm run build` clean.
- **Depends-on:** none

### T-238 In-browser layout viewer — SVG/Canvas, KLayout-style pan/zoom/layers
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** React component that renders a parsed GDS-II (via T-237) in the browser using Canvas (for polygon-heavy designs) with an SVG overlay for selection and measure tools. Pan/zoom (KLayout-style: middle-mouse drag, scroll-wheel zoom to cursor, fit-to-window), a layers panel with per-layer colour + visibility (driven by the PDK layer map when available — T-239), polygon-pick → display layer / datatype / vertex-count / area, ruler tool (`r` key) for measure-distance, hierarchy panel showing top cell + children. **Not a klayout-GUI in the browser** — a clean re-render against our own data model.
- **Target files/packages:** `src/components/LayoutViewer.jsx` (NEW), `src/components/LayoutViewer.test.jsx` (NEW), `src/components/LayoutViewerLayers.jsx` (NEW — layers panel), `src/components/LayoutViewerHierarchy.jsx` (NEW), `src/lib/gdsLoader.js` (NEW — fetch a parsed GDS payload from the backend), `src/lib/layoutCanvas.js` (NEW — pure rendering logic, no DOM coupling), `src/lib/layoutCanvas.test.js` (NEW — vitest on the rendering math), `packages/kerf-silicon/src/kerf_silicon/routes_layout.py` (NEW — HTTP route that streams a parsed GDS to the frontend as JSON-polygons).
- **Definition of Done:** loading the SKY130 inverter fixture renders ≥ 1 visible polygon per layer; pan/zoom math: clicking at canvas-coord (200,150) at zoom=2x with origin (-100,-50) projects to layout-coord (200,200) (oracle); the layers panel toggles layer visibility and the canvas re-renders without lag (< 16 ms per frame on the inverter fixture); polygon-pick highlights the selection; vitest + pytest oracles; `npm run build` clean.
- **Depends-on:** T-237

### T-239 Skywater SKY130 PDK integration (Apache-licensed PDK)
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** integrate the **SKY130** open PDK. We do not bundle the 4 GB PDK in the repo — we ship a `kerf silicon pdk install sky130` CLI that clones `github.com/google/skywater-pdk` (Apache 2.0) to `~/.kerf/pdks/sky130/`, then exposes its contents to the rest of the silicon stack: the standard-cell `.lef` (T-240) + `.lib` (T-241) for OpenROAD/OpenLane; the device-model `.spice` files for T-236; the layer map (`layers.json`) for T-238's layers panel; the design rules (DRC deck — for T-244). Same pattern as `kerf-render`'s Blender install path. Sentinel + clear "run `kerf silicon pdk install sky130`" hint when the PDK is absent. v1 = SKY130 only; GF180MCU and IHP SG13G2 are deferred to follow-up tickets once SKY130 ships.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/pdk/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/pdk/sky130.py` (NEW — fetch + layout of the PDK directory), `packages/kerf-silicon/src/kerf_silicon/pdk/registry.py` (NEW — registered PDKs + paths), `packages/kerf-silicon/src/kerf_silicon/pdk/layers.py` (NEW — KLayout-style `.lyp` → JSON layer map), `packages/kerf-cli/src/kerf_cli/commands/silicon_pdk.py` (NEW — `kerf silicon pdk install sky130`), `packages/kerf-silicon/tests/test_pdk.py` (NEW — git clone mocked), `packages/kerf-silicon/llm_docs/pdk.md` (NEW — how to install + which PDKs are supported).
- **Definition of Done:** `kerf silicon pdk install sky130` (with git clone mocked) creates the directory layout + a `~/.kerf/pdks/sky130/manifest.json` record; the `registry` module returns `Path("~/.kerf/pdks/sky130")` for `"sky130"`; layer-map: at least 50 named layers loaded; missing-PDK returns sentinel; pytest oracles; `npm run build` clean.
- **Depends-on:** none

### T-240 LEF (Library Exchange Format) reader — standard-cell abstracts
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** pure-Python reader for **LEF** (Library Exchange Format) — the standard-cell + macro abstract format consumed by OpenROAD. Two flavours: **technology LEF** (process layers, design rules) and **cell LEF** (per-cell pin abstracts, obstructions, sizes). Spec is the public Cadence LEF/DEF Language Reference. Reader produces dataclass trees; integrates with the T-239 PDK so `from kerf_silicon.pdk import sky130; sky130.cells` returns the parsed cell library. No writer in v1 (OpenROAD generates LEF; we read).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/layout/lef/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/lef/reader.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/lef/ast.py` (NEW), `packages/kerf-silicon/tests/test_lef.py` (NEW), `packages/kerf-silicon/tests/fixtures/lef/sky130_fd_sc_hd.tech.lef` (NEW — slim subset, ~50 layers), `packages/kerf-silicon/tests/fixtures/lef/sky130_fd_sc_hd.cells.lef` (NEW — slim subset, ~20 cells).
- **Definition of Done:** technology LEF parses ≥ 50 layers with the expected `LAYER li1 TYPE ROUTING` shape; cell LEF parses ≥ 20 cells with at least `sky130_fd_sc_hd__inv_1` / `sky130_fd_sc_hd__nand2_1` / `sky130_fd_sc_hd__dfxtp_1` present and pin counts matching the oracle; the inverter cell has the expected `WIDTH`/`HEIGHT` values; pytest oracles; `npm run build` clean.
- **Depends-on:** T-239

### T-241 Liberty (`.lib`) timing-library reader — characterised cell timing
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** pure-Python reader for **Liberty** (`.lib`) — the standard cell timing/power characterisation format. Spec is the public Synopsys Liberty Reference Manual; the format is a nested `key (value) { … }` grammar. Parses per-cell `cell` blocks containing `pin` blocks containing `timing` arcs with `cell_rise` / `cell_fall` / `rise_transition` / `fall_transition` lookup tables, plus `leakage_power` and `internal_power`. Dataclass tree. Reader-only in v1.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/layout/liberty/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/liberty/reader.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/layout/liberty/ast.py` (NEW), `packages/kerf-silicon/tests/test_liberty.py` (NEW), `packages/kerf-silicon/tests/fixtures/liberty/sky130_fd_sc_hd__tt_025C_1v80.lib` (NEW — slim subset, ~10 cells, 1 PVT corner).
- **Definition of Done:** Liberty fixture parses ≥ 10 cells; the inverter cell has a `cell_rise` LUT with the expected `index_1` (input slew) and `index_2` (output cap) axes; cell-leakage-power values are read as floats in the expected range (~1 pW for SKY130 HD); pytest oracles; `npm run build` clean.
- **Depends-on:** T-239

### T-242 OpenROAD / OpenLane subprocess flow — RTL → GDS-II (Phase 2 epic — split later)
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** **Phase 2 epic — split later.** subprocess wrapper around the **OpenROAD / OpenLane** flow that takes RTL (`.v` / `.sv` / `.vhd` via Yosys+GHDL plugin) + a target PDK (`sky130A` via T-239) + a top-module name + a clock period, and produces a real `.gds` mask file + STA reports + DRC report + power report. Internally a multi-stage flow (synthesis via Yosys, floorplan, place, CTS, route, finalise — all OpenROAD), each emitting an intermediate artefact. Streams logs back as they arrive. Tape-out-proven flow (600+ chips on SKY130/GF180 via Efabless MPWs as of 2026). Missing-binary path returns sentinel + Docker install hint (`docker pull efabless/openlane:latest`). Cloud-worker path (deferred): pre-bake OpenLane into a sibling of the `Dockerfile.cycles-worker` image. This ticket is intentionally large; create sub-tickets T-242a..T-242f when picked up: (a) flow config schema, (b) Yosys-stage wiring (reuse T-234), (c) floorplan+place+CTS+route stages, (d) report extraction (STA/DRC/power), (e) Docker worker image, (f) hosted-job billing tie-in (`kerf_paid` minute-metering).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/flow/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/flow/openlane.py` (NEW — top-level orchestrator), `packages/kerf-silicon/src/kerf_silicon/flow/config.py` (NEW — `kerf.silicon.json` flow config schema), `packages/kerf-silicon/src/kerf_silicon/flow/stages/` (NEW — one module per stage), `packages/kerf-silicon/src/kerf_silicon/flow/reports.py` (NEW — extract STA/DRC/power from OpenROAD logs), `packages/kerf-render/Dockerfile.openlane-worker` (NEW — sibling of cycles-worker, pre-bakes OpenLane + Yosys + Magic + Netgen + KLayout), `packages/kerf-silicon/tests/test_openlane_flow.py` (NEW — subprocess mocked + a real-OpenLane integration test gated on docker presence).
- **Definition of Done:** with mocked subprocess, the orchestrator produces stage outputs in the expected order and emits a structured progress event per stage; with the OpenLane Docker image available (integration test gated), a 32-bit counter RTL takes a `.v` source + `sky130A` PDK + a 100 MHz target clock through the full flow and emits a non-empty `.gds`, a non-empty STA report whose `slack` field parses as a float, and a DRC summary with a non-negative `violations` count; missing-OpenLane returns sentinel + install hint; pytest oracles; `npm run build` clean.
- **Depends-on:** T-234, T-235, T-239, T-240

### T-243 Schematic-to-mask flow — `.sch` → place-cells → `.gds`
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Phase-3 capability: take a transistor-level schematic (re-use the `kerf-electronics` schematic graph data model where applicable, with an MOS device extension) → solve a basic placement → place stock-cell footprints from the PDK → emit `.gds`. The bridge between hand-drawn analog/mixed-signal schematics and a mask layout, complementary to RTL→GDS-II via OpenLane (T-242). v1 scope: small mixed-signal blocks (op-amps, bandgaps, comparators) at ≤ 50 devices; no auto-routing yet (routing is T-244-adjacent).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/sch2mask/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/sch2mask/place.py` (NEW — simple force-directed placer), `packages/kerf-silicon/src/kerf_silicon/sch2mask/instantiate.py` (NEW — emit `.gds` cell references from the placer output), `packages/kerf-silicon/src/kerf_silicon/sch2mask/devices.py` (NEW — MOS device extension to the schematic model), `packages/kerf-silicon/tests/test_sch2mask.py` (NEW), `packages/kerf-silicon/tests/fixtures/sch2mask/two_stage_opamp.sch.json` (NEW).
- **Definition of Done:** the two-stage op-amp fixture (7 MOS devices) places without overlap, instantiates the corresponding SKY130 cells, and writes a `.gds` that loads in T-238's viewer and re-reads via T-237 with cell-count = 7; placer converges in < 100 iterations; pytest oracles; `npm run build` clean.
- **Depends-on:** T-237, T-239, T-240

### T-244 DRC (Design Rule Check) engine
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Phase-3 capability: a **DRC engine** that takes a `.gds` + a DRC deck (per-PDK rules expressed as a structured `rules.json` with min-width / min-spacing / min-enclosure / min-area constraints per layer or layer-pair) and emits a list of violations as `{rule, layer, polygon_a, polygon_b?, location, message}`. v1 implements the geometric primitives: width (single-polygon min-edge-distance), spacing (between-polygon min-distance on a layer), enclosure (one layer must enclose another by ≥ X), area (min polygon area). Reuses the polygon-ops library that we will need anyway (point-in-polygon, polygon-polygon distance) — wire to the existing `kerf-cad-core` 2D geometry if it covers what we need, otherwise add a small `silicon/poly_ops.py`. PDK rules come from the SKY130 install (T-239) as a translated `rules.json`.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/drc/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/drc/engine.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/drc/rules.py` (NEW — rule schema + loaders), `packages/kerf-silicon/src/kerf_silicon/drc/poly_ops.py` (NEW — width/spacing/enclosure/area primitives), `packages/kerf-silicon/src/kerf_silicon/pdk/sky130_drc.json` (NEW — translated SKY130 DRC deck, slim subset), `packages/kerf-silicon/tests/test_drc.py` (NEW), `packages/kerf-silicon/tests/fixtures/drc/violations_known.gds` (NEW — handcrafted violations).
- **Definition of Done:** the known-violations fixture produces ≥ 3 violations of the expected rule names + locations; a clean fixture produces 0 violations; min-width primitive flags a 50 nm wire on a 60 nm-min layer; min-spacing flags two 80 nm-apart wires on a 100 nm-min layer; pytest oracles; `npm run build` clean.
- **Depends-on:** T-237, T-239

### T-245 LVS (Layout vs Schematic) — netlist extraction + comparison
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Phase-3 capability: **LVS** — extract a device-level netlist from a `.gds` (via shape connectivity + layer recognition rules per PDK) and compare to the schematic netlist (T-243's data model). Implements (1) connectivity extraction (which polygons on routing layers connect to which device pins via vias/contacts), (2) device recognition (a layer-shape pattern → MOSFET / cap / res), (3) graph-isomorphism comparison between extracted and schematic netlists with device-type + connectivity match. v1 = MOSFET-only on SKY130. Adapter to **Magic VLSI**'s ext-format if/when we want to compare against a reference flow.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/lvs/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/lvs/extract.py` (NEW — connectivity + device extraction), `packages/kerf-silicon/src/kerf_silicon/lvs/compare.py` (NEW — graph-isomorphism), `packages/kerf-silicon/src/kerf_silicon/lvs/recognition.py` (NEW — MOS pattern recognition), `packages/kerf-silicon/tests/test_lvs.py` (NEW), `packages/kerf-silicon/tests/fixtures/lvs/inverter_match.gds` + `inverter_match.sch.json` (NEW — should match), `packages/kerf-silicon/tests/fixtures/lvs/inverter_mismatch.gds` + `inverter_mismatch.sch.json` (NEW — one wire deliberately swapped).
- **Definition of Done:** the matched-inverter pair returns `lvs_clean=True` with 0 reported diffs; the mismatched pair returns `lvs_clean=False` with the swapped wire identified by both device-pin and net; MOS device recognition extracts 2 MOSFETs from the inverter layout; pytest oracles; `npm run build` clean.
- **Depends-on:** T-237, T-239, T-243

### T-246 Parasitic extraction (RC) — post-layout net capacitance + resistance
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Phase-3 capability: **parasitic extraction** — read a routed `.gds` + a per-PDK extraction deck (layer sheet-resistance Ω/sq, layer-to-substrate cap fF/μm², layer-to-layer cap fF/μm²) and emit a per-net `{R[], C[]}` SPICE-compatible parasitic netlist (`.spef` standard format). Drives back-annotated SPICE simulation (T-236) for real post-layout timing. v1 = lumped C and lumped R per net (not distributed RC tree); SKY130 deck only.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/extract/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/extract/parasitics.py` (NEW — area/perimeter integration → C + R), `packages/kerf-silicon/src/kerf_silicon/extract/spef_writer.py` (NEW — IEEE 1481 SPEF format), `packages/kerf-silicon/src/kerf_silicon/pdk/sky130_extract.json` (NEW — sheet-R + cap per layer), `packages/kerf-silicon/tests/test_extract.py` (NEW).
- **Definition of Done:** the inverter routed fixture extracts a per-net cap ≥ 0.1 fF and ≤ 10 fF (oracle range for that geometry on SKY130 met1); the SPEF output parses by `spef2spice` or our own re-reader; pytest oracles; `npm run build` clean.
- **Depends-on:** T-237, T-239

### T-247 Photolithography mask generation — fracturing + OPC stub
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped
- **Scope:** Phase-3 capability: **photolithography mask generation** — take a finalised `.gds` and produce mask-shop deliverables. Two pieces: (1) **fracturing** — convert curvilinear / 45° polygons to rectilinear primitives (rectangles / trapezoids) compatible with mask-writer formats (MEBES, JEOL51); (2) **OPC stub** — placeholders for Optical Proximity Correction (hammerheads, serifs, scattering bars) implemented as a rule-based transform on layer boundaries. v1 OPC is a stub (rule-based corner-rounding only); production OPC needs model-based OPC which is a multi-quarter project — explicitly out of scope. The fracturing piece is genuinely useful at v1 because it is a deterministic geometric transform.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/mask/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/mask/fracture.py` (NEW — polygon → rectangles/trapezoids), `packages/kerf-silicon/src/kerf_silicon/mask/opc_stub.py` (NEW — rule-based corner corrections), `packages/kerf-silicon/src/kerf_silicon/mask/mebes_writer.py` (NEW — minimal MEBES stub), `packages/kerf-silicon/tests/test_mask.py` (NEW).
- **Definition of Done:** an L-shaped polygon fractures to 2 rectangles with no area loss; the OPC stub adds hammerheads at line-ends matching a 3-rule deck; mask writer emits a syntactically-valid MEBES stub that re-reads to the same shape set; pytest oracles; `npm run build` clean.
- **Depends-on:** T-237

### T-248 File-kind enum + extension wiring for silicon/EDA + firmware (deferred migration)
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped
- **Scope:** consolidated deferred migration that folds the new file-kinds + extensions into the kerf-core 0001 baseline (per the [clean baseline migrations](../decisions.md) policy — **no `alter table add column` shims**). New kinds added to `files_kind_check`: `firmware_project` (`.fw.json` / `kerf.fw.json` — distinct from the existing `firmware` kind which covers the `.ino` sketch path), `hdl_vhdl` (`.vhd` / `.vhdl`), `hdl_verilog` (`.v` / `.sv`), `spice_netlist` (`.spice` / `.cir`), `gds_layout` (`.gds`), `oasis_layout` (`.oas`), `lef_lib` (`.lef`), `def_design` (`.def`), `liberty_lib` (`.lib`), `silicon_flow` (`.silicon.json` — the OpenLane flow config from T-242), `silicon_pdk` (folder kind for `~/.kerf/pdks/<name>/`). File-extension → kind mapping lives in `packages/kerf-core/src/kerf_core/file_kinds.py` (or wherever the existing mapping currently lives); add Monaco syntax modes for the new HDL extensions wired into the T-116 plain-highlight path (basic keyword highlighting only — full LSP later).
- **Target files/packages:** `packages/kerf-core/src/kerf_core/db/migrations/0001_core_identity.sql` (edit the `files_kind_check` constraint — fold, do **not** add `alter` shims), `packages/kerf-core/src/kerf_core/db/models/models.py` (sync the `CheckConstraint` literal), `packages/kerf-core/src/kerf_core/file_kinds.py` (edit — add the new extensions), `src/lib/monaco/vhdlMode.js` (NEW), `src/lib/monaco/verilogMode.js` (NEW), `src/lib/monaco/spiceMode.js` (NEW), `packages/kerf-core/tests/test_file_kinds.py` (edit — assert new extensions resolve correctly).
- **Definition of Done:** a fresh DB reset includes the new kinds in `files_kind_check`; the SQLAlchemy `CheckConstraint` literal matches exactly (lint test); `file_kinds.resolve("alu.vhd")` returns `hdl_vhdl`; `file_kinds.resolve("inverter.gds")` returns `gds_layout`; the Monaco language registration runs without error on a synthetic `.vhd` file; pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-230 (the firmware-side `kerf.fw.json` kind), T-231 (VHDL), T-232 (Verilog), T-236 (SPICE), T-237 (GDS), T-240 (LEF), T-241 (Liberty), T-242 (silicon flow config)

