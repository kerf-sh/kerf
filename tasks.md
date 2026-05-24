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

## Tier A — Storage hygiene + comprehensive Git UX (P0, 2026-05-19)

These tasks together complete the **"git is the user-facing history surface;
file_revisions is invisible plumbing"** model. After this workstream lands,
the only history UI a user sees is the Git tab (commits / branches / diffs /
graph); `file_revisions` keeps backing Cmd+Z but never appears as a feature.
Sequenced for parallel execution across 5 Sonnet agents.

### T-300 Drop History tab from right drawer; preserve Cmd+Z plumbing

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Right drawer just gained a History tab on top of `file_revisions`.
  With git becoming the user-facing snapshot story, this surface is
  redundant. Cmd+Z / Cmd+Shift+Z still drive `file_revisions` underneath,
  but as invisible plumbing — the user never sees a revision list as a feature.
- **Target files:** `src/routes/Editor.jsx`, `src/store/workspace.js`,
  `src/__tests__/rightDrawer.test.jsx`.
- **Definition of Done:**
  - Editor.jsx removes the History tab + its body render
  - `openRevisionDrawer` / `closeRevisionDrawer` become no-ops or remap to nothing
  - Topbar Undo / Redo + Cmd+Z keyboard shortcut still work against `file_revisions`
  - rightDrawer test pinned: Chat/Activity/Git tabs present, History absent
- **Effort:** S
- **Depends-on:** none

### T-301 Activity feed: hide keystroke-level edits

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** With file_revisions invisible, the activity feed should stop
  spamming per-keystroke `'edit'` rows. Keep meaningful tool/llm/restore
  edits; drop bare `source='user'` keystroke noise.
- **Target files:** `packages/kerf-api/src/kerf_api/routes.py` (activity SQL),
  `packages/kerf-api/tests/test_activity_route.py`.
- **Definition of Done:**
  - Activity SQL UNION clause for `'edit'` rows filters `source <> 'user'`
    (keep `llm`, `tool`, `restore` — those are meaningful assistant actions)
  - Regression test: 30 `source='user'` edits produce 0 activity rows;
    `source='llm'` / `source='tool'` still appear
- **Effort:** S
- **Depends-on:** none

### T-302 Revisions: size estimator endpoint + Git-tab badge

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Before a destructive purge (T-303), users need to see how much
  space file_revisions are taking. A small read-only endpoint + UI badge
  satisfies this and ships independently.
- **Target files:** `packages/kerf-api/src/kerf_api/routes.py`,
  `src/lib/api.js`, `src/cloud/GitPanel.jsx`.
- **Definition of Done:**
  - `GET /api/projects/{pid}/revisions/size` returns
    `{total_bytes, revision_count, by_file: [{file_id, file_name, bytes, count}]}`
  - Uses `pg_column_size(content_gz)` + `octet_length(content)` to estimate
  - Auth + workspace-role check
  - `src/lib/api.js` adds `getRevisionsSize(projectId)`
  - GitPanel.jsx renders an unobtrusive badge: "Revision history: 4.2 MB across
    230 revisions [Manage…]"
  - Backend route test + frontend render test
- **Effort:** S
- **Depends-on:** none

### T-303 Revisions: purge endpoint + confirmation modal

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Users want to free DB space after their work is committed to
  git. Must be loud and safe — purging is unrecoverable, so the modal
  must require an "Everything I want to keep is committed" confirmation.
- **Target files:**
  - `packages/kerf-core/src/kerf_core/revisions.py` (purge helper)
  - `packages/kerf-api/src/kerf_api/routes.py` (DELETE route)
  - `src/components/PurgeRevisionsModal.jsx` (new)
  - `src/cloud/GitPanel.jsx` (open-modal wiring)
- **Definition of Done:**
  - `purge_project_revisions(pool, project_id, keep_last_per_file=5)` keeps
    most recent N revisions per file as a safety net; deletes the rest +
    nullifies any storage blobs they owned
  - `DELETE /api/projects/{pid}/revisions?keep_last=N&confirm=PURGE`
    rejects without `confirm=PURGE` (defence-in-depth)
  - require_editor (owners/editors only)
  - Modal shows pre-purge size (from T-302), requires
    "[ ] I have committed everything I want to keep" checkbox, big red button
  - Post-purge toast: "Freed 4.2 MB. Git commits are unaffected."
  - Backend tests: keeps the keep_last per file, rejects without confirm,
    requires editor role
- **Effort:** M
- **Depends-on:** T-302 (uses the size badge to open the modal)

### T-304 Git: commit graph + per-commit diff viewer

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Comprehensive git UX starts with a clear visual of branches /
  merges and a way to inspect what each commit changed.
- **Target files:**
  - `src/cloud/GitGraph.jsx` (new)
  - `src/cloud/CommitDiffViewer.jsx` (new)
  - `src/cloud/GitPanel.jsx` (swap bare commit list)
  - `packages/kerf-api/src/kerf_api/routes_git_diff.py` (already exists;
    confirm or add per-commit diff endpoint)
- **Definition of Done:**
  - GitGraph renders SVG with lanes per branch, commits as circles,
    merge as connecting line; reads `gitCommits` + `gitBranches` from store
  - `GET /api/projects/{pid}/git/commits/{sha}/diff` returns
    `{files: [{path, status, additions, deletions, hunks?}]}`
  - CommitDiffViewer is a modal opened by clicking a commit in the graph
  - Tests: graph render, diff fetch, modal interaction
- **Effort:** M-L
- **Depends-on:** none

### T-305 Git: staged-changes view + per-file diff before commit

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Today the Git tab has a bare "commit message + commit" button.
  Users want to SEE what's changing before they commit — diff per file.
- **Target files:**
  - `src/cloud/StagedChanges.jsx` (new)
  - `src/cloud/GitPanel.jsx` (top-of-tab section)
  - `packages/kerf-api/src/kerf_api/routes.py` (new `/git/status`)
- **Definition of Done:**
  - `GET /api/projects/{pid}/git/status` returns
    `{changed_files: [{path, status: 'added'|'modified'|'deleted', additions, deletions}]}`
    by diffing live `files` table state vs latest commit tree
  - StagedChanges renders the list with click-to-expand per-file diff
  - GitPanel shows "Staged changes (3 files)" section above the commit input;
    commit button label updates as the count changes
  - Tests: backend route + StagedChanges render
- **Effort:** M
- **Depends-on:** none (but lands cleanly next to T-304)

### T-307 Clean baseline migrations: fold all alter/drop into CREATE TABLE

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** The 12 consolidated migrations still carry dozens of
  `alter table … add column`, `alter table … drop constraint`, and
  `alter table … drop column` shims. The "DBs are reset on deploy"
  contract means none of those alters are reachable from a fresh schema
  — they're noise that confuses readers and silently breaks the
  "single source of truth = the CREATE TABLE literal" rule. Audit each
  file and fold every alter back into the original CREATE TABLE that
  owns the table; remove drop-column / drop-constraint shims entirely
  (they were undoing earlier mistakes in an older migration set that
  no longer exists in this codebase).
- **Target files:** `packages/kerf-core/src/kerf_core/db/migrations/*.sql`
  (all 12 files).
- **Definition of Done:**
  - `grep -nE "^\s*(alter table|drop table|drop column|drop index|drop constraint)" packages/kerf-core/src/kerf_core/db/migrations/*.sql` returns ZERO matches
  - Every column added by a prior `alter table add column` is present in
    the relevant `create table if not exists` block at the file where the
    table is originally created
  - For each table, find the originating CREATE TABLE and fold every
    subsequent `add column` into it (handle the column-order carefully
    — append at the end before `created_at`/`updated_at` so the diff is
    readable)
  - `drop constraint` + `add constraint` pairs collapse into the single
    final constraint inside the CREATE TABLE block
  - Run `python -m kerf_core.db.migrations.runner` against a fresh
    schema (the deploy-time path) and assert all 12 migrations apply
    cleanly + zero errors
  - Existing baseline tests (`test_activity_attribution_schema.py`,
    `test_files_version_column.py`, `test_chat_messages_is_error_column.py`,
    etc.) continue to pass — those tests look at the CREATE TABLE block
    and will catch fold mistakes
  - New test `test_migrations_no_alter_drop.py` pins the
    grep-returns-zero invariant
- **Effort:** L (mechanical but careful; one file at a time)
- **Depends-on:** none (pure refactor)

### T-308 Tool-architecture collapse: 30+ narrow → ~12 sharp tools

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Per the claude-code-guide research (in
  `docs/architecture/runtime-state-audit.md` followups), Claude Code
  ships ~10 generic tools that compose. Kerf currently registers 30+
  per-plugin narrow tools (cam.run, fem.*, render.*, electronics.*, plc.*,
  silicon.* …). Each extra tool is system-prompt tokens, decision
  surface, and a failure point (numpy/OCC missing → load failures).
  Collapse into ~12 sharp tools:
    - **File ops:** read_file, write_file, edit_file, list_files,
      search_files (one Glob/Grep-style)
    - **Scaffolding:** create_file (replaces create_sketch / create_part
      / create_feature / create_circuit / create_assembly /
      create_drawing — single tool with `kind` arg + Anthropic JSON
      Schema enum)
    - **Compute:** run_compute (single tool, `engine` arg dispatches
      to fem / cfd / spice / cam / render / topo) + poll_compute
    - **Docs:** search_kerf_docs (stays)
    - **Geometry queries:** describe_part (single read-only inspector
      for any kind)
  All existing tool *implementations* stay; only their *registration
  surface* collapses.
- **Target files:**
  - `packages/kerf-chat/src/kerf_chat/llm.py` (the CATALOG of tool specs)
  - Every plugin's tool registration site (`packages/*/src/*/plugin.py`)
  - `packages/kerf-api/src/kerf_api/routes.py` (the dispatch loop in
    `_run_tool` or equivalent) — single dispatcher reads the new
    arg-shape and routes to the underlying implementation
- **Definition of Done:**
  - `tool_choice`/`tools` array sent to Anthropic has ≤ 14 entries
    (allow some headroom; today's count >30)
  - All existing tool integration tests still pass (the underlying
    implementations are unchanged; only the dispatcher contract changes)
  - New test `test_tool_surface_size.py` pins the upper bound
  - Documentation update: `docs/architecture/tool-surface.md` lists the
    12 final tools + the engine-arg enum for the unified dispatchers
- **Effort:** L
- **Depends-on:** none (frontend chat UI is unchanged — it just receives
  fewer tool_use blocks; same render path)

### T-311 Streaming chat (SSE): tool-use visible in real time

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** `POST /messages` is request/response — server runs the
  entire LLM loop (Anthropic call + tool exec + Anthropic call + … ),
  then returns one JSON blob. The user waits 20-40 s on a multi-tool
  exchange and sees nothing but "Kerf is thinking…". Stream the
  response so each step is visible as it happens.
- **Choice:** Server-Sent Events. One-way server→client over plain
  HTTP; works through Fly proxies; no connection upgrade. Anthropic's
  own streaming protocol maps to SSE cleanly. NOT WebSocket — no
  bidirectional need.
- **Target files:**
  - `packages/kerf-chat/src/kerf_chat/llm.py` — `AnthropicProvider.stream()`
    yielding events from `client.messages.stream(...)`. Map Anthropic's
    `content_block_delta` / `message_start` / `message_stop` /
    `input_json_delta` to a small Kerf-native event enum so other
    providers can be wrapped the same way (OpenAI, etc).
  - `packages/kerf-api/src/kerf_api/routes.py` — new
    `POST /api/projects/{pid}/threads/{tid}/messages/stream` returning
    `StreamingResponse(media_type="text/event-stream")`. The dispatcher
    loop emits SSE frames after each provider event AND around each
    tool execute (start / running / result).
  - `src/lib/sseClient.js` (new) — small wrapper around `fetch()` +
    ReadableStream that yields parsed SSE events. EventSource doesn't
    support POST, so we use fetch + body-stream-reader.
  - `src/store/workspace.js` — `sendMessage` now opens the stream,
    feeds events into an in-progress assistant message + tool-message
    list; updates the store on each event. `sending: true` flips off
    only at `message_done`.
  - `src/components/ChatPanel.jsx` — replace the bare "Kerf is
    thinking…" with a live tool-use list. Each tool gets a chip with
    a status icon: `🌀 running` / `✓ done` / `⚠ error`. Final text
    streams in word-by-word into the assistant message body.
- **Event schema** (Kerf-native, provider-agnostic):
  ```
  event: assistant_text_delta
  data: {"text": " on it"}
  ```
  ```
  event: tool_use_start
  data: {"tool_use_id": "tu_...", "name": "read_file", "input_partial": {...}}
  ```
  ```
  event: tool_executing
  data: {"tool_use_id": "tu_..."}
  ```
  ```
  event: tool_result
  data: {"tool_use_id": "tu_...", "is_error": false, "content_preview": "..."}
  ```
  ```
  event: assistant_done
  data: {"stop_reason": "end_turn", "input_tokens": 1234, "output_tokens": 567}
  ```
  ```
  event: error
  data: {"message": "...", "is_error": true}
  ```
- **Backward compatibility:** keep the existing non-streaming
  `POST /messages` endpoint for the test suite + any non-streaming
  client. Frontend prefers the stream endpoint and falls back to the
  blocking one on EventStream failure.
- **Cancellation:** if the user clicks "Stop", the client aborts the
  fetch; the server `asyncio.CancelledError` halts the LLM call.
  Persist whatever assistant text was streamed up to that point
  (don't lose partial output).
- **Definition of Done:**
  - Multi-tool exchange (read_file → edit_file → write_file)
    surfaces each tool as a chip immediately
  - Assistant text streams in token-by-token (Anthropic delta events
    forwarded)
  - Tool errors propagate via `event: tool_result` with
    `is_error: true` — UI shows the red error chip; assistant turn
    continues
  - Stop button cancels the stream + persists partial state
  - Existing `POST /messages` non-streaming endpoint still works
    (regression: legacy test suite passes)
- **Tests:**
  - `packages/kerf-api/tests/test_messages_stream_route.py` — fake
    Anthropic stream yields known events; assert SSE frames come out
    in order; assert one tool round-trip emits start / executing /
    result events
  - `packages/kerf-chat/tests/test_anthropic_stream.py` — provider
    layer mapping
  - `src/lib/__tests__/sseClient.test.js` — parse SSE frames from a
    mock ReadableStream
  - `src/store/__tests__/sendMessageStream.test.js` — store state
    transitions per event
  - `src/components/__tests__/ChatPanel.toolChips.test.jsx` —
    tool-use chips render with correct status icons
- **Effort:** L
- **Depends-on:** none (the `is_error: true` plumbing from T-308 is
  reused)

### T-312 Always initialise new projects on a `main` branch

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Auto-git-init (`ensure_git_repo`) inserts into
  `cloud_git_repos` with `default_branch = 'main'`, BUT there's no
  corresponding `cloud_git_branches` row created. The branch picker
  starts empty until the user makes their first commit. Fix:
  populate `cloud_git_branches('main', null, true)` on init so the
  picker shows the branch immediately. Also: never default to `master`
  or any other name. Always `main`.
- **Target files:**
  - `packages/kerf-cloud/src/kerf_cloud/routes.py` — extend
    `ensure_git_repo` to also INSERT a `('main', NULL, true)` row
    into `cloud_git_branches` (`ON CONFLICT DO NOTHING` for
    idempotency)
  - Tests
- **Definition of Done:**
  - Newly-created project has a `main` row in `cloud_git_branches`
    with `is_default = true` and `head_sha` null until the first commit
  - Branch picker on a fresh project shows "main" instead of empty
  - Test: `test_auto_git_init_creates_main_branch.py` asserts the row
    exists after create_project
  - `ensure_git_repo` remains idempotent (calling twice doesn't dupe)
- **Effort:** S
- **Depends-on:** none

### T-313 Project deletion cascades: DB rows + S3 blobs + git tree

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** `DELETE /api/projects/{pid}` exists but the cascade is
  partial. FK constraints clean some tables (`files`, `chat_threads`,
  `cloud_git_repos` if cascade is set) but not all. Critically: the
  Tigris S3 blobs that own file content and the in-storage git objects
  are NOT cleaned up — they leak forever, eating quota + cost. When a
  user deletes a project they expect everything to go.
- **Target files:**
  - `packages/kerf-core/src/kerf_core/db/migrations/0001_core_identity.sql`
    + other baseline migrations — audit every FK that references
    `projects(id)`; ensure each is `ON DELETE CASCADE`. Fold into the
    CREATE TABLE per the clean-baseline rule.
  - `packages/kerf-api/src/kerf_api/routes.py` (or kerf-cloud routes)
    — extend the `DELETE /projects/{pid}` handler to:
      1. Collect all `storage_key`s belonging to project's `files`
      2. Call `storage.delete()` for each (Tigris S3)
      3. Collect `derived_artifacts`/`blob_objects` keys; delete them
      4. Delete the git repo's S3 prefix
         (`workspaces/{ws}/git/{project_id}/` or whatever the
         convention is in `storage/git_storer.py`)
      5. Finally DELETE from projects; FKs cascade the rows
- **Definition of Done:**
  - Create a project with N files + a commit + photos
  - Delete the project
  - Assert: `files`, `chat_threads`, `chat_messages`, `file_revisions`,
    `cloud_git_repos`, `cloud_git_branches`, `cloud_git_commits` all
    have zero rows for that project_id
  - Assert: Tigris S3 bucket has zero objects under the project's
    storage prefixes (mock the storage layer)
  - All baseline FK constraints to `projects(id)` use
    `ON DELETE CASCADE`; `grep` confirms
  - Test: `test_delete_project_cascade.py` covers the full sequence
- **Effort:** M
- **Depends-on:** T-307 invariant (clean baseline; this task folds
  FK changes into baseline rather than adding alter shims)

---

## Tier A — Strategic spine, broken down from ROADMAP §3 + §3.5 (2026-05-20)

ROADMAP-level commitments that hadn't yet been turned into agent-sized
tasks. Sequenced for the autonomous-loop / next contributor. Effort
estimates: **S** = ½ day, **M** = 1-2 days, **L** = 3-5 days, **XL** =
1-2 weeks (split into sub-tasks before pulling).

### T-320 Large-assembly performance ceiling + LOD / lazy-load (P0-5)

✅ shipped (2026-05-20) · **Tier A · P0** (FPS/heap targets modelled — no GPU in CI; decimation + frustum-cull + LOD-swap logic verified)

- **Why:** ROADMAP §3 P0-5 — mechanical / architecture / automotive
  personas hit a perf cliff above ~1000 parts. Automotive
  full-vehicle DMU (10,000s of parts) is the extreme case. Today's
  viewport renders every part fully; no LOD, no lazy-load, no
  measured budget.
- **Definition of Done:**
  - A perf-harness script under `scripts/perf_assembly.py` that
    loads N synthetic parts (N ∈ {100, 1k, 5k, 10k}) and reports
    FPS + time-to-interactive + memory peak in a headless renderer
  - LOD pipeline: each part gets a coarse-mesh proxy auto-generated
    from its OCCT tessellation (e.g. quadric-edge-collapse to ~10 %
    triangle budget); viewport swaps to proxy when angular size <
    threshold
  - Lazy-load: assembly components are loaded only when their
    bounding box intersects the camera frustum + an N-component
    pre-fetch window
  - 5k-part assembly: ≥ 30 FPS interactive in a hosted Chrome run,
    ≤ 1.5 GB heap
  - 10k-part assembly: ≥ 15 FPS, ≤ 3 GB heap
  - Test fixture: a synthesized 10k bolt-grid `.assembly` that the
    perf harness can replay
- **Target files/packages:** `src/lib/lod.js`, `src/lib/assemblyLoader.js`,
  `packages/kerf-cad-core/src/kerf_cad_core/mesh_decimate.py` (if not
  shipped), `scripts/perf_assembly.py`, `tests/perf/test_large_assembly.py`.
- **Effort:** L
- **Depends-on:** none (assembly + OCCT tess shipped)

### T-321 Broaden text / code file support (P0-6)

✅ shipped (2026-05-20) · **Tier A · P0**

- **Why:** ROADMAP §3 P0-6 — common text / source files (`.txt`,
  `.md`, `.c`, `.cpp`, `.h`, `.hpp`, `.py`, `.js`, `.ts`, `.json`,
  `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.sh`, `.ino`/`.uno`,
  `.ld`, `.v`, `.vhd`, …) should open as editable text **now**;
  per-language syntax highlighting follows. Architecture-independent;
  every persona benefits.
- **Definition of Done:**
  - `files.kind` enum gains `'text'` (fold into baseline 0001 — no
    alter shim; the kind check constraint already accepts a long list)
  - File-upload + create_file UX detects any of the extensions above
    and assigns `kind='text'`
  - The CodeMirror-backed editor accepts the kind and loads the
    content as plain text editable; existing JSCAD-specific
    machinery does NOT fire for these
  - Syntax highlighting bootstraps from CodeMirror's bundled language
    modes — start with python / cpp / verilog / vhdl / yaml / toml /
    bash; others fall back to plaintext
  - Tool dispatcher (`read_file` / `write_file` / `edit_file`) treats
    `kind='text'` identically to `'file'` (the JSCAD kind)
  - Tests: per-extension fixture upload → renders as editable text;
    edit_file works against a `.py` file
- **Target files/packages:**
  `packages/kerf-core/src/kerf_core/db/migrations/0001_core_identity.sql`,
  `packages/kerf-core/src/kerf_core/classify.py` (extension → kind),
  `src/lib/codeMirrorSetup.js` (language pickers),
  `src/routes/Editor.jsx` (text-kind branch),
  `packages/kerf-api/tests/test_text_files.py` (new).
- **Effort:** M
- **Depends-on:** T-307 (clean baseline) so the new kind folds in.

### T-322 Project export / materialize foundation — `kerf export` / `import` (P0-7)

✅ shipped (2026-05-20) · **Tier A · P0**

- **Why:** ROADMAP §1.5 commitment 3 — "you own your data and can
  leave any time" is only credible if there's a concrete `kerf
  export` / `kerf import` that produces and ingests a plain file
  tree. The git-substrate work (T-307+) gives us the data model; this
  task gives users the tool to leave with it.
- **Definition of Done:**
  - CLI `kerf export <project-id> --out <dir>` writes the project's
    materialized tree (files + .kerf/metadata.json + .kerf/manifest.lock)
    to disk; preserves git history if the project has a cloud_git_repo
  - CLI `kerf import <dir>` reverses it: creates a fresh project +
    re-creates the file tree from the directory; round-trips losslessly
  - Round-trip test: export → wipe local DB → import → diff with
    original = empty
  - `.kerf/manifest.lock` records file SHAs + the cloud_git_repos
    default_branch + workspace_id mapping (anonymised if exporting
    across owners)
  - Symmetric: cloud project export / self-hosted project import work
    with identical CLI; documented in `docs/architecture/portability.md`
- **Target files/packages:**
  `packages/kerf-cli/src/kerf_cli/export.py` (new),
  `packages/kerf-cli/src/kerf_cli/import.py` (new),
  `packages/kerf-cli/tests/test_export_import_roundtrip.py` (new),
  `docs/architecture/portability.md` (new).
- **Effort:** L
- **Depends-on:** T-313 (delete cascade) — same FK audit informs the
  materialize logic.

### T-323 3D in-vehicle wiring harness — route through DMU (P1-7)

✅ shipped (2026-05-20) · **Tier A · P1**

- **Why:** ROADMAP §3 P1-7 — automotive / ECAD personas need 3D
  routing through the digital mock-up. Today only 2D WireViz
  `.wiring` diagrams. Without a 3D harness, automotive cannot
  deliver a "harness-installed" milestone.
- **Definition of Done:**
  - `.harness` file kind (folded into baseline kind check)
  - Routing solver: given a 3D assembly + a list of (from-pin,
    to-pin, gauge, max-bend-radius) edges + an obstacle set, finds
    a Manhattan-ish polyline through the DMU avoiding bodies
  - Bundle / segment / connector libraries (≥ 20 standard automotive
    parts: Mil-DTL-38999, Deutsch DT, Molex Mini-Fit, …)
  - Formboard flatten: 3D harness → 2D flat pattern + length table
  - Length / gauge / voltage-drop report: per-circuit total length,
    gauge from current rating, voltage drop at nominal current
  - Test fixture: 4-wire harness through a 3-box obstacle set →
    flattens within ±2 mm of the 3D path length; voltage drop matches
    analytic prediction within 5 %
- **Target files/packages:**
  `packages/kerf-electronics/src/kerf_electronics/harness3d/` (new
  module), `packages/kerf-electronics/tests/test_harness3d.py`.
- **Effort:** XL — should be split into T-323a (routing solver),
  T-323b (formboard flatten), T-323c (libraries + voltage drop)
  before being pulled.
- **Depends-on:** assemblies, electronics, mates (all shipped).

### T-324 Local folder sync + cloud↔self-host portability (P1-10)

✅ shipped (2026-05-20) · **Tier A · P1**

- **Why:** ROADMAP §1.5 commitment 3 — `kerf sync` two-way folder
  mirror. Complements T-322's one-shot export/import with a live
  ongoing mirror so users can edit in their favourite editor on disk
  and have it round-trip back to the cloud project.
- **Definition of Done:**
  - CLI `kerf sync <project-id> <local-dir>` starts a foreground
    daemon that watches both sides, propagates changes either way
  - OCC (T-302) prevents clobber: if both sides changed the same file
    between two ticks, the daemon stops + prints a conflict report
  - Symmetric: works against the hosted cloud OR a self-hosted Kerf
    server identically
  - Test: simulate a 3-file project, edit on disk, expect the next
    sync tick to upload; edit in the cloud, expect the next tick to
    download
  - `docs/cli/kerf-sync.md`
- **Target files/packages:** `packages/kerf-cli/src/kerf_cli/sync.py`
  (new), `packages/kerf-cli/tests/test_sync_daemon.py`.
- **Effort:** L
- **Depends-on:** T-322 (export/import), T-302 (OCC).

### T-325 1D system simulation — Modelica / Amesim / Simulink class (sim pillar)

✅ shipped (2026-05-20) · **Tier A · P1**

- **Why:** ROADMAP §3.5 — lumped-parameter thermal / hydraulic /
  electrical / control networks. Modelica is **text**, a declarative
  equation-based language — exceptionally AI-native. Today: absent.
- **Definition of Done:**
  - `.system` file kind (folded into baseline kind check)
  - DSL or .mo subset: components + connections defined as text;
    parser → DAE
  - DAE solver: BDF + initialization (Pantelides + dummy-derivatives)
    via `scipy.integrate.solve_ivp` for index-1 systems; document
    fall-back / known limits for higher-index
  - Component library: thermal mass / resistance / capacitance,
    hydraulic orifice / pump / tank, electrical R/L/C/source,
    control P/PI/PID — 20 components minimum
  - Validation: RC low-pass step response matches analytic
    `Vout(t) = Vin·(1−e^(−t/τ))` within 1 %; mass-spring-damper free
    response matches `e^(−ζω_n t)·cos(ω_d t)` within 2 % over 5 s
  - Round-trip with shipped `flight_dynamics/sixdof.py` for a
    plant + PID-controlled aircraft model
- **Target files/packages:** `packages/kerf-systems/` (new package),
  `packages/kerf-systems/src/kerf_systems/{parser,solver,components}/`,
  `packages/kerf-systems/tests/test_systems_*.py`.
- **Effort:** XL — split into T-325a (parser), T-325b (DAE solver),
  T-325c (component library), T-325d (oracles) before pulling.
- **Depends-on:** none.

### T-326 Manufacturing process simulation — mold-flow / casting / stamping (sim pillar)

✅ shipped (2026-05-20) · **Tier A · P2**

- **Why:** ROADMAP §3.5 — Moldflow / MAGMASOFT / AutoForm / Vericut
  class. Closes the loop between design intent and a producible part
  the LLM can reason about. Verified absent.
- **Definition of Done (v1, narrow scope to keep this M not XL):**
  - Pick ONE flagship sub-domain for v1: **mold-flow** (injection
    moulding fill simulation, generalized Hele-Shaw approximation)
  - Inputs: shell mesh + gate location + polymer rheology card
    (Cross-WLF viscosity) + injection pressure / temperature
  - Output: fill-time map + weld-line prediction + short-shot
    detection
  - v1 explicitly out of scope: residual stress, warp, fibre
    orientation — flagged in a follow-up
  - Validation: a flat disc with central gate fills with radial
    symmetry; an L-shaped part shows the expected weld line at the
    corner
- **Target files/packages:** `packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/`
  (new), `packages/kerf-manufacturing/tests/test_moldflow.py`.
- **Effort:** L
- **Depends-on:** OCCT tess (shipped).

### T-327 Automatic Feature Recognition (AFR) — STEP → editable feature tree (sim pillar)

✅ shipped (2026-05-20) v1 · **Tier A · P1** — pure-Python AAG engine recognises 11 features (through/blind hole, counterbore, countersink, pocket, slot, boss, fillet, chamfer, rib, step) → ordered editable feature_tree; 27 tests green; LLM tool afr_recognize_features. **Deferred to T-327b:** revolve/sweep/loft, pattern features, real-STEP round-trip + Hausdorff oracle (needs headless OCCT).

- **Why:** ROADMAP §3.5 — "edit ANY model" enabler. Today, an
  imported "dumb" STEP is read-only B-rep; the LLM cannot
  parametrize / edit it. AFR turns it back into a `.feature` tree
  the LLM can reason about. **Single largest AI-leverage unlock left
  on the roadmap.**
- **Definition of Done (v1):**
  - Recognise the 5 canonical features: extrude, revolve, hole,
    chamfer, fillet
  - Algorithm: face-attribute graph → known-pattern matchers
    (planar-circular-hole detector, cylindrical-coaxial-pair detector,
    edge-curvature chamfer/fillet detector)
  - Output: a `.feature` JSON tree that, when re-evaluated, produces
    the same B-rep (within tessellation tolerance)
  - Round-trip oracle: load `bracket.step` → recognise → re-evaluate
    → diff Hausdorff distance ≤ 1e-3 × bounding-box diagonal
  - Limits documented: sweeps / lofts / pattern features deferred
    to v2
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/afr/`
  (new), `packages/kerf-cad-core/tests/test_afr.py`,
  `packages/kerf-cad-core/tests/fixtures/afr/bracket.step`.
- **Effort:** XL — split into T-327a..d (graph builder, hole detector,
  chamfer/fillet detector, extrude/revolve detector) before pulling.
- **Depends-on:** OCCT, feature evaluator (shipped).

### T-328 Knowledge-based engineering — code-compliance / DriveWorks-class rules

✅ shipped (2026-05-20) · **Tier A · P2**

- **Why:** ROADMAP §3.5 — KBE rule engine driven by the model
  (Eurocode / AISC / ACI / ASME / ISO). Rules + standards are text,
  hugely AI-native, and a large differentiator. Today: only narrow
  PCB-DRC + railing checks exist.
- **Definition of Done (v1 narrow):**
  - Rule DSL: declarative `kerf-rule` files defining checks
    (`when <model-predicate> then <assertion>`)
  - Engine: load rule files → evaluate against a project (file tree +
    metadata) → emit a structured violation list
  - Ship 30 rules across 3 domains: AISC steel-column slenderness,
    Eurocode 2 reinforcement-spacing, ASME B18 fastener-grade selection
  - Surfaced in chat: `validate_against_rules(project, rule_pack)`
    LLM tool
  - Test: a model that violates AISC column-slenderness produces a
    citing violation; a compliant model produces zero
- **Target files/packages:** `packages/kerf-rules/` (new package),
  `packages/kerf-rules/rules/{aisc,eurocode2,asme_b18}/*.yaml`.
- **Effort:** L
- **Depends-on:** none.

### T-329 3D tolerance / variation analysis — 3DCS / CETOL class

✅ shipped (2026-05-20) · **Tier A · P1**

- **Why:** ROADMAP §3.5 — shipped 1D worst-case / RSS / Monte-Carlo
  in `kerf-mates` `tolerance.py`. Need to extend to **3D**: statistical
  stack-up + contributor analysis in 3D.
- **Definition of Done:**
  - Inputs: assembly + datum reference frames + per-feature
    GD&T-style tolerances (position / orientation / form)
  - Monte-Carlo: sample N variants from the feature tolerance
    distributions, compute final-assembly KPIs (gap / step / parallelism)
  - Output: histograms + contributor sensitivities (sorted by
    variance contribution)
  - Validation: a 4-block stack with ±0.1 mm flatness each →
    expected gap σ matches the RSS analytic stack-up within 5 %
- **Target files/packages:**
  `packages/kerf-mates/src/kerf_mates/tolerance3d.py` (new),
  `packages/kerf-mates/tests/test_tolerance3d.py`.
- **Effort:** L
- **Depends-on:** mates (shipped), 1D tolerance.py (shipped).

### T-330 PLM depth — 150% / effectivity BOM, where-used, ECR/ECO, MBSE/SysML trace

✅ shipped (2026-05-20) · **Tier A · P1**

- **Why:** ROADMAP §3.5 — shipped: file revisions + cloud git +
  configurations + BOM rollup. Missing: configurator UX, 150% /
  effectivity BOM, where-used queries, ECR/ECO change-management,
  MBSE/SysML traceability. The digital thread is structured data +
  relationships = ideal for an LLM to traverse and keep coherent.
- **Definition of Done:**
  - `bom_150_percent(project, effectivity_date)` returns the
    full universe of parts ever used + per-part effectivity windows
  - `where_used(part_id)` walks the assembly graph and returns every
    parent assembly + effectivity
  - `.eco` file kind: structured change request with from-state +
    to-state + impact list (where-used roll-up)
  - SysML-light: `.sysml` file kind, top-level requirement + trace
    links to file IDs + verification test IDs; a `trace` query
    returns the requirement → implementation → verification chain
  - Surfaced as LLM tools so the assistant can reason about the
    change graph
- **Target files/packages:** `packages/kerf-cloud/src/kerf_cloud/plm/`
  (new), `packages/kerf-cloud/tests/test_plm_*.py`.
- **Effort:** XL — split into T-330a (150% BOM), T-330b (where-used),
  T-330c (ECO file kind), T-330d (SysML trace) before pulling.
- **Depends-on:** BOM, file_revisions, cloud git (all shipped).

### T-331 Multi-CAD interop + geometry healing — AP242 / JT / Parasolid / QIF

✅ shipped (2026-05-20) v1 · **Tier A · P1** — AP242 PMI/datum/GD&T text-level reader → drawing annotations + heal_geometry LLM tool (weld/unify-normals/fill-holes/remove-degenerate); 56 tests. **Deferred to T-331b:** JT reader, Parasolid bridge (pyOCCT, license-required-at-runtime), QIF reader.

- **Why:** ROADMAP §3.5 — STEP I/O shipped. Missing: AP242
  (semantic GD&T / PMI), JT (Siemens), Parasolid (.x_t / .x_b), QIF
  (Quality Information Framework). Plus a general geometry-healing
  pass (only internal ShapeFix usage today, not a public tool).
- **Definition of Done:**
  - AP242 reader extracts PMI annotations + datum reference frames
    + GD&T tolerances and maps to `.drawing` annotations
  - JT reader (single-file CAD format, structured / faceted) — at
    minimum read the geometry + the assembly tree
  - Parasolid bridge via `pyOCCT` (Parasolid kernel is closed; ship
    the bridge with a documented "license required at runtime")
  - QIF reader for inspection plans
  - `heal_geometry(file_id)` LLM tool: closes gaps, removes
    short edges, fixes face orientation; reports the diff
  - Test: an intentionally broken STEP file (one degenerate face)
    passes through heal_geometry and re-exports cleanly
- **Target files/packages:** `packages/kerf-imports/src/kerf_imports/{ap242,jt,parasolid,qif}_reader.py`
  (new), `packages/kerf-cad-core/src/kerf_cad_core/heal.py` (new).
- **Effort:** XL — split per format before pulling.
- **Depends-on:** OCCT, kerf-imports.

### T-332 Reverse-engineering pipeline — point cloud → parametric solid

✅ shipped (2026-05-20) v1 · **Tier A · P2**

- **Why:** ROADMAP §3.5 — Geomagic / PolyWorks class. Today: absent
  as a pipeline. Adjacent building blocks (`quad_remesh.py`) exist.
- **Definition of Done (v1):**
  - `.pcd` / `.ply` import → segmentation (RANSAC for planes +
    cylinders + spheres + cones)
  - Per-segment feature fit → `.feature` tree (extrudes, revolves,
    primitives)
  - Round-trip: a known synthetic cube + cylinder point cloud →
    recognise → re-evaluate → Hausdorff diff ≤ 1e-3
  - Documented limits: freeform / class-A surfaces deferred to v2
- **Target files/packages:**
  `packages/kerf-cad-core/src/kerf_cad_core/reverse_engineering/` (new),
  tests + fixtures.
- **Effort:** XL — point-cloud handling is its own world.
- **Depends-on:** OCCT, AFR (T-327) for the fit→feature step.

### T-332b Reverse-engineering pipeline v2 — deferred sub-capabilities

✅ shipped (2026-05-20) · **Tier A · P2** — binary PLY/PCD (LE+BE) parsers, statistical-outlier noise filter + Laplacian smoothing, cone LM refinement (≤0.0008° half-angle), torus RANSAC (≤0.6% R/r); 166 tests. **Still deferred (OCC/NURBS-blocked):**

- **Topology / feature ordering** — constructive history reconstruction
  (which feature is additive vs. subtractive) requires an OCC Boolean
  evaluation pass (depends on T-327 AFR).
- **Freeform / Class-A surfaces** — NURBS patch fitting for unrecognised
  regions (depends on T-100 / T-101 NURBS surfacing).

### T-327b Automatic Feature Recognition v2 — deferred sub-capabilities

🔴 not started · **Tier A · P1**

Deferred from T-327 v1 (shipped 2026-05-20). Pick up any/all of:

- **Revolve / sweep / loft recognition** — extend the AAG matchers beyond the
  11 prismatic/local features to swept solids.
- **Pattern features** — linear / circular array detection (collapse repeated
  feature instances into a single parametric pattern node).
- **Real-STEP round-trip + Hausdorff oracle** — load a genuine `bracket.step`
  via a headless OCCT loader, recognise → re-evaluate the feature tree → write
  STEP back, and assert Hausdorff distance ≤ 1e-3 × bbox-diagonal against the
  original B-rep. **Depends on headless OCCT bindings** being available at test
  time (the v1 oracle is self-contained synthetic topology fixtures).
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/afr/`
  (extend `recognize.py`), `packages/kerf-cad-core/tests/test_afr.py`.
- **Depends-on:** T-327 (shipped), OCCT bindings.

### T-331b Multi-CAD interop v2 — JT / Parasolid / QIF readers

🔴 not started · **Tier A · P1**

Deferred from T-331 v1 (shipped 2026-05-20). Pick up any/all of:

- **JT reader** (Siemens) — single-file CAD format, structured + faceted; at
  minimum read the geometry + assembly tree.
- **Parasolid bridge** (`.x_t` / `.x_b`) via pyOCCT — the Parasolid kernel is
  closed, so ship the bridge with a documented "license required at runtime"
  sentinel when the kernel is absent.
- **QIF reader** — Quality Information Framework inspection plans → structured
  annotations (extends the AP242 PMI work).
- **Target files/packages:**
  `packages/kerf-imports/src/kerf_imports/{jt,parasolid,qif}_reader.py` (new).
- **Depends-on:** T-331 (shipped), OCCT / pyOCCT bindings for Parasolid.

### T-333 Mechanism synthesis — MotionGen / Adams class linkage / cam / gear synthesis

✅ shipped (2026-05-20) · **Tier A · P2**

- **Why:** ROADMAP §3.5 — synthesis is an inverse problem stated in
  text (motion spec → mechanism), exceptionally AI-native. Today:
  mates constraint solver shipped (`packages/kerf-mates/solver.py`);
  synthesis 🔴.
- **Definition of Done (v1):**
  - 4-bar linkage synthesis from a 3-point motion specification
    (Burmester theory)
  - Cam-profile synthesis from a follower-motion law (cycloidal,
    polynomial, harmonic) — verify shipped under T-262 motion
    domain; if not, ship here
  - Gear-train synthesis: given a target ratio + speed range,
    return a 1- or 2-stage spur configuration with module / tooth
    counts / centre distance
  - Validation: a synthesized 4-bar that traces 3 specified
    coupler-curve points within 0.5 mm
- **Target files/packages:** `packages/kerf-mates/src/kerf_mates/synthesis/`
  (new).
- **Effort:** L
- **Depends-on:** mates solver (shipped).

### T-334 Sustainability / LCA — embodied carbon + circularity from the model

✅ shipped (2026-05-20) · **Tier A · P2**

- **Why:** ROADMAP §3.5 — One Click LCA class. Data-native,
  increasingly *mandated* by regulation. Today: absent.
- **Definition of Done:**
  - Materials database with embodied-carbon factors (kg CO₂-eq / kg)
    for 50+ common materials — wire to existing material catalogue
    (`packages/kerf-mates/material*.py` if it exists, else create)
  - `lca_report(project)` LLM tool: walks the BOM, multiplies mass
    × factor per part, returns total embodied carbon + per-material
    breakdown + circularity score (% recycled content, end-of-life
    recyclability)
  - Tests against published reference values (e.g. ICE database for
    steel ~1.8 kg CO₂-eq/kg, concrete ~0.12, aluminium ~9, …) within
    ±5 %
- **Target files/packages:** `packages/kerf-lca/` (new package),
  `packages/kerf-lca/data/ice_v3.json` (or similar).
- **Effort:** M
- **Depends-on:** BOM + material catalogue.

---



✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Public-SaaS Kerf bills credits per LLM call and proxies
  Anthropic tokens. Without rate limiting, a single user (malicious or
  buggy script) can drain credits, exhaust the Anthropic per-key
  rate limit (affecting *every* other user), or DoS expensive endpoints.
  The architecture audit (`docs/architecture/runtime-state-audit.md`)
  flagged this as missing.
- **Design:** Postgres-first sliding window. Single dependency function
  `enforce_rate_limit(key, max_requests, window_seconds)` used as a
  FastAPI dependency on the hot endpoints. Storage in a new tiny table
  with TTL-style cleanup. Multi-machine safe by definition (Postgres
  is the shared store). Migrate to Fly-managed Upstash Redis only when
  observed QPS proves Postgres can't keep up — same call site, swap
  the backend.
- **Target files:**
  - `packages/kerf-core/src/kerf_core/db/migrations/0001_core_identity.sql`
    — fold a `rate_limit_buckets` table into baseline (NO alter shim):
    ```
    create table if not exists rate_limit_buckets (
        bucket_key  text not null,
        window_start timestamptz not null,
        count       integer not null default 0,
        primary key (bucket_key, window_start)
    );
    create index rate_limit_buckets_window_idx
        on rate_limit_buckets(window_start);
    ```
  - `packages/kerf-core/src/kerf_core/rate_limit.py` (new) — helper:
    ```python
    async def enforce(pool, key: str, max_per_window: int,
                      window_seconds: int = 60) -> None:
        # Sliding window via INSERT ... ON CONFLICT (bucket_key,
        # window_start) DO UPDATE SET count = count + 1 RETURNING count.
        # window_start truncates to window_seconds. On count > max,
        # raises HTTPException 429 with Retry-After header.
    ```
  - `packages/kerf-core/src/kerf_core/dependencies.py` (or kerf-api
    equivalent) — `rate_limit_dependency(max=..., window=...)` factory
    that builds a FastAPI dependency function keyed on
    `user_id`-or-`ip`. Compose into existing `require_auth` dependency
    chain.
  - **Hot endpoints to gate:**
    - `POST /auth/login` → 10/min per IP
    - `POST /auth/register` → 5/hour per IP
    - `POST /projects/{pid}/threads/{tid}/messages` → 30/min per user
      (LLM token burn; also subject to the byo-vs-paid bucket gate)
    - `POST /api/projects/{pid}/files/{fid}/photos` → 60/min per user
      (uploads)
    - `POST /api/projects/{pid}/git/push` → 10/min per project
- **GC worker:** existing `kerf-billing.BlobGCWorker` pattern — add a
  small `RateLimitGCWorker` that deletes rate_limit_buckets rows older
  than 24 hours, runs every 15 min. Or use a Postgres TRIGGER on insert
  to clean up older windows for the same key.
- **Definition of Done:**
  - `rate_limit_buckets` table present in baseline 0001 (no alter shim)
  - `enforce_rate_limit` helper exists with full test coverage:
    - first request under limit returns immediately
    - request that crosses the limit raises HTTPException 429 with
      Retry-After header
    - concurrent requests from same key are correctly serialised by
      Postgres (no over-allowance)
    - windowing is sliding (a request 61 s after the first counts in
      a fresh window)
  - The 5 hot endpoints listed above are gated, each with a clear
    per-route limit constant
  - Integration test: 11 rapid requests to `/auth/login` from the same
    IP — the 11th returns 429
  - 429 responses carry a useful body: `{detail: "rate limit exceeded",
    retry_after: 12}` so the frontend can show a sensible toast
  - Frontend: `src/lib/api.js` `request()` handles 429 — surfaces a
    toast "Too many requests — try again in N seconds" rather than
    failing silently
  - GC worker registered + tested (single row written, then 24h+
    later the cleanup pass removes it)
  - Docs: brief note in `docs/architecture/rate-limiting.md` explaining
    the design + when to migrate to Redis
- **Effort:** M
- **Depends-on:** T-307 (clean baseline for the new column)

### T-309 IndexedDB localStash wiring (crash-recovery for unsaved edits)

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** Per the architecture audit (`docs/architecture/runtime-state-audit.md`),
  the localStash infrastructure (`src/lib/localStash.js` + auto-save
  scheduler + dirty-store) is fully built and unit-tested — but
  **never called from any editor**. Editors call `api.updateFile()`
  directly, bypassing IDB. Crash-tab recovery doesn't work today even
  though all the code exists. Wire it.
- **Target files:**
  - `src/lib/localStash.js` (fix the wrong-arity `flush()` bug — line 90
    calls `stash(workspaceId, filePath)` with 2 args expecting bytes
    back; the function is write-only)
  - `src/lib/autosaveScheduler.js` (the orphan scheduler)
  - `src/store/workspace.js` — `saveFile` / `markDirty` paths call
    `stash` on every edit; `flushDirty` runs on a debounce and pushes
    to the server
  - `src/main.jsx` — `reconcile()` on startup checks IDB for
    unflushed entries and either pushes them OR prompts the user
    ("You have unsaved changes from a previous session — restore?")
  - Editor mount/unmount: register on dirty, deregister on unmount
- **Definition of Done:**
  - Type 5 keystrokes, close the tab without saving, reopen → editor
    restores the 5 keystrokes from IDB (or prompts "Restore unsaved
    changes?")
  - `dirtyStore.count` reflects the actual pending IDB entries
  - `flush()` arity bug fixed: `localStash` exposes a `getBytes(workspaceId, path)`
    read function paired with the write-only `stash()`
  - Tests: `localStash.test.js`, `autosaveScheduler.test.js`,
    `dirtyStore.test.js`, plus a new integration test
    `editorAutosave.test.jsx` that simulates an unload + reopen
  - Architecture audit's "gap" bullet for IndexedDB save is closed
- **Effort:** M
- **Depends-on:** none

---

### T-306 Git: branch picker + push/pull state polish

✅ shipped (2026-05-19) · **Tier A · P0**

- **Why:** The branch picker is a flat dropdown today. Add visual cues for
  diverging commits, sync state, "create new branch" affordance.
- **Target files:**
  - `src/cloud/BranchPicker.jsx` (new)
  - `src/cloud/GitPanel.jsx` (swap existing branch element)
  - `packages/kerf-cloud/src/kerf_cloud/routes.py` (extend `/git/branches`)
- **Definition of Done:**
  - BranchPicker dropdown: current branch with check; per-branch
    ahead-by-N / behind-by-N when remote is configured; inline
    "Create new branch"; "Delete branch" (with confirm) on non-current
  - Backend: `/git/branches` returns `{name, head_sha, is_default, ahead, behind}`
    when remote is configured (pygit2 calc)
  - Push / Pull buttons show "synced" / "N ahead" / "N behind" badges
  - Tests: branch list shape, picker interaction
- **Effort:** M
- **Depends-on:** none (lands cleanly next to T-304, T-305)

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
- **Status:** ✅ shipped (2026-05-20) — all sub-tasks T-100a..h complete.
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
- **Status:** ✅ shipped (2026-05-20) — all sub-tasks T-101a..f complete.
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
- **Status:** ✅ shipped (2026-05-20) — all sub-tasks T-104a..h complete.
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

### T-322 `kerf export` / `kerf import` — project portability (materialized tree)
- **Tier:** A
- **Priority:** P0
- **Status:** ✅ shipped (2026-05-20) · **Tier A · P0**
- **Scope:** `kerf export <project-id> --out <dir>` materialises the full
  project as a plain directory tree with `.kerf/metadata.json` (project
  name, IDs, tags) and `.kerf/manifest.lock` (per-file SHA-256 OIDs,
  cloud_git_repo default_branch, workspace_id_hint). `kerf import <dir>`
  reverses the operation losslessly. Both commands are symmetric across
  cloud and self-hosted instances.
- **Target files:**
  - `packages/kerf-cli/src/kerf_cli/export.py`
  - `packages/kerf-cli/src/kerf_cli/import_.py`
  - `packages/kerf-cli/tests/test_export_import_roundtrip.py`
  - `docs/architecture/portability.md`
- **Definition of Done:** export writes files + `.kerf/metadata.json` +
  `.kerf/manifest.lock`; import reverses losslessly; round-trip test
  (export → wipe → import → diff = empty) passes; manifest.lock records
  file SHAs + cloud_git_repo default_branch + workspace_id hint; pytest
  32 tests green.
- **Depends-on:** T-128 (existing ZIP spine)

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
- **Status:** ✅ shipped — `- [x] **GK-48**` *Landed: io/step_write.py, 43 tests.*
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

### T-160b GK P2: IGES 144 trimmed-surface reader/writer (GK-49)
- **Tier:** B
- **Money/reach rationale:** IGES interop (trimmed NURBS surfaces) is a critical import/export path for legacy CAD data. Entity-144 is the trimmed-surface subset used by the vast majority of mechanical CAD IGES exports.
- **Priority:** P2
- **Status:** ✅ shipped — `- [x] **GK-49**` *Landed: io/iges.py, 28 tests.*
- **Scope:** Pure-Python `geom/io/iges.py` — IGES 5.3 reader/writer for entity-144 (Trimmed Parametric Surface) + dependents (128 NURBS surface, 126 NURBS curve, 142 curve-on-surface). Write→read round-trip boundary loop Hausdorff ≤ `1e-6`. No OCCT; no external binaries; hermetic tests.
- **Target files/packages:** `packages/kerf-cad-core/src/kerf_cad_core/geom/io/__init__.py` (new package), `packages/kerf-cad-core/src/kerf_cad_core/geom/io/iges.py` (new), `packages/kerf-cad-core/tests/test_iges.py` (new, 28 tests).
- **Definition of Done:** trimmed plane round-trip boundary Hausdorff ≤ `1e-6`; surface CPs exact to `1e-9`; 80-column IGES line formatting; pytest hermetic; ties GK-49.
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


## Silicon Phase 4 — verification, optimisation, post-silicon (T-249 … T-258)

**Strategic frame** (ROADMAP §3.5b): Phase 1+2+3 (T-231..T-248) shipped the RTL front-end, layout back-end, and a first pass of verification/characterisation (DRC, LVS, parasitic extraction, mask generation). Phase 4 closes the depth gap between "we have a flow" and "tape-out-ready industrial chip design" — the layer where Cadence / Synopsys / Mentor charge $1M / seat / year. Each ticket is independently usable; T-249/T-250/T-251 are the headline path (testbench → power → timing closure) and T-256/T-257 are the headline customer wins (anyone can submit to Tiny Tapeout / Caravel from a chat session).

### T-249 Cocotb-compatible Python testbench harness for VHDL/Verilog simulators
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** pure-Python testbench harness that mirrors **Cocotb**'s public API (`cocotb.test`, `dut.signal.value`, `await Timer(10, 'ns')`, `await RisingEdge(dut.clk)`, `await Combine(...)`, `cocotb.fork`) so existing cocotb tests run unchanged against either the T-233 behavioural VHDL simulator *or* the T-235 GHDL bridge *or* the Verilator subprocess (added here, separate from yosys). A `Dut` proxy wraps the simulator's signal table and provides `__getattr__` access to hierarchical signals; an `await`-driven scheduler co-operates with the T-233 delta-cycle queue so test coroutines suspend on simulated time. v1 = single-clock single-DUT designs; multi-clock + cross-language top-level deferred to a follow-up. Verilator path: `verilator --trace --cc <files> --exe <harness>` then build and `subprocess.run(./obj_dir/V<top>)` with a Unix-socket bridge that the Python harness drives.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/cocotb/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/cocotb/runner.py` (NEW — discovers `@cocotb.test` decorated functions), `packages/kerf-silicon/src/kerf_silicon/cocotb/dut.py` (NEW — `Dut` proxy + signal-handle), `packages/kerf-silicon/src/kerf_silicon/cocotb/triggers.py` (NEW — `Timer`, `RisingEdge`, `FallingEdge`, `Edge`, `ReadOnly`, `Combine`, `First`), `packages/kerf-silicon/src/kerf_silicon/cocotb/clock.py` (NEW — `Clock` driver), `packages/kerf-silicon/src/kerf_silicon/cocotb/backends/native.py` (NEW — drives T-233), `packages/kerf-silicon/src/kerf_silicon/cocotb/backends/ghdl.py` (NEW — drives T-235), `packages/kerf-silicon/src/kerf_silicon/cocotb/backends/verilator.py` (NEW — Verilator subprocess + Unix-socket bridge), `packages/kerf-silicon/tests/test_cocotb_runner.py` (NEW), `packages/kerf-silicon/tests/test_cocotb_triggers.py` (NEW), `packages/kerf-silicon/tests/fixtures/cocotb/test_counter4.py` (NEW — verifies the T-231 4-bit-counter fixture).
- **Definition of Done:** `test_counter4.py` (an unmodified cocotb test that asserts the counter rolls 0→15→0 over 16 rising edges) passes against the native backend; against the GHDL backend (when GHDL is on `$PATH`) it produces the same trace; against the Verilator backend (when verilator is on `$PATH`) it produces the same trace; `Timer(10, 'ns')` suspends a coroutine exactly 10 ns of simulated time; `RisingEdge(clk)` fires once per posedge; missing-simulator returns the sentinel + install hint and never raises; pytest oracles; `npm run build` clean.
- **Depends-on:** T-233, T-235

### T-250 Power analysis — switching activity × capacitance from T-246 parasitics + T-241 Liberty
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** pure-Python power-analysis pass that consumes (1) a switching-activity file (`.saif`, standard IEEE 1801 format — read-only in v1) produced by gate-level simulation, (2) the per-net capacitance from T-246's SPEF, (3) the per-cell `internal_power` and `leakage_power` from T-241's Liberty parser, and computes total power = **dynamic** (`Σ ½ × C_net × V² × f × α`, summed over nets, with α = toggle-rate from SAIF) + **internal** (`Σ Liberty.internal_power[cell] × toggle_rate[cell]`) + **leakage** (`Σ Liberty.leakage_power[cell]`). Emits a per-instance + per-net + total breakdown JSON. v1 = single-corner (TT 25 °C 1.8 V); multi-corner Pareto deferred. SAIF reader is the IEEE 1801 P&G grammar — a simple S-expression-like nested form.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/power/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/power/saif_reader.py` (NEW — IEEE 1801 SAIF parser), `packages/kerf-silicon/src/kerf_silicon/power/analyse.py` (NEW — `analyse_power(netlist, spef, liberty, saif) -> PowerReport`), `packages/kerf-silicon/src/kerf_silicon/power/report.py` (NEW — JSON report writer), `packages/kerf-silicon/tests/test_power_analysis.py` (NEW), `packages/kerf-silicon/tests/fixtures/power/inverter_chain.saif` (NEW — handcrafted SAIF with a known toggle rate), `packages/kerf-silicon/tests/fixtures/power/inverter_chain_expected.json` (NEW — analytic-oracle expected report).
- **Definition of Done:** for an inverter chain of 4 cells with a 50 % toggle rate, total dynamic power matches `½ × C × V² × f × α` analytically within 1 %; leakage power matches `Σ Liberty.leakage_power` exactly; SAIF reader extracts at least the `T0`, `T1`, `TC` fields per net; sentinel + install hint when SPEF/Liberty/SAIF inputs are missing; pytest oracles; `npm run build` clean.
- **Depends-on:** T-241, T-246

### T-251 Timing closure — static timing analysis on a Liberty-characterised netlist
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** pure-Python **static timing analysis** (STA) pass: take a gate-level netlist (T-234 JSON output) + a Liberty timing library (T-241) + an optional SPEF (T-246) + an SDC file (Synopsys Design Constraints — `create_clock`, `set_input_delay`, `set_output_delay`, `set_max_delay`, `set_min_delay`, `set_false_path`, `set_multicycle_path`). Computes per-path arrival-time + required-time + slack via lookup-table interpolation over Liberty `cell_rise` / `cell_fall` / `rise_transition` / `fall_transition` arcs. Reports the worst-slack-per-endpoint and worst-N-paths. v1 = single-corner, single-clock, no on-chip variation; OCV / multi-corner deferred. SDC reader is a simple Tcl-subset parser (`set`-free single-statement form is enough for v1).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/sta/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/sta/sdc_reader.py` (NEW — minimal Tcl-subset SDC parser), `packages/kerf-silicon/src/kerf_silicon/sta/graph.py` (NEW — timing-graph construction from netlist + Liberty), `packages/kerf-silicon/src/kerf_silicon/sta/propagate.py` (NEW — forward arrival + backward required, NLDM LUT interpolation), `packages/kerf-silicon/src/kerf_silicon/sta/report.py` (NEW — per-path / per-endpoint report writer), `packages/kerf-silicon/tests/test_sta.py` (NEW), `packages/kerf-silicon/tests/fixtures/sta/counter4_sky130.netlist.json` (NEW — post-synth netlist from T-234), `packages/kerf-silicon/tests/fixtures/sta/counter4.sdc` (NEW — 100 MHz clock), `packages/kerf-silicon/tests/fixtures/sta/counter4_expected_report.json` (NEW — analytic oracle).
- **Definition of Done:** the counter4 fixture STA at a 100 MHz clock produces a worst-slack value in `[+0.5 ns, +5 ns]` (Liberty data for SKY130 high-density at TT 25 °C is well-bounded); per-path report extracts ≥ 4 register-to-register paths; SDC `set_input_delay -clock clk 2` shifts arrival by 2 ns at the input port; NLDM LUT interpolation matches the analytic linear-interp value at the four corner taps exactly; pytest oracles; `npm run build` clean.
- **Depends-on:** T-234, T-241, T-246

### T-252 Clock-tree synthesis (CTS) seed
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** pure-Python **clock-tree synthesis** seed that takes a placed netlist (T-242 floorplan output) + a set of clock sinks (registers in the netlist) + a target skew bound, and builds a buffered clock tree minimising skew. v1 algorithm = **H-tree** (recursive midpoint-split of the bounding box, buffer inserted at each branching point); a buffer-sizing pass uses Liberty (T-241) `cell_rise`/`cell_fall` to pick the smallest buffer cell whose drive strength meets the per-segment capacitance budget. Emits an updated netlist + a per-sink skew report. v1 ignores process variation; OCV-aware CTS deferred. This is **seed-quality** — production tape-outs would use OpenROAD's TritonCTS for this stage; the seed lets us reason about clock topology without that dependency.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/cts/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/cts/htree.py` (NEW — recursive midpoint-split algorithm), `packages/kerf-silicon/src/kerf_silicon/cts/buffer_sizing.py` (NEW — Liberty-driven buffer-cell selection), `packages/kerf-silicon/src/kerf_silicon/cts/skew_report.py` (NEW), `packages/kerf-silicon/tests/test_cts.py` (NEW), `packages/kerf-silicon/tests/fixtures/cts/counter4_placed.netlist.json` (NEW — placed netlist with 4 register sinks).
- **Definition of Done:** the counter4 placed fixture (4 register sinks at known coordinates) produces an H-tree with exactly 2 levels of branching + 3 buffers inserted; reported max-skew between any two sinks ≤ 50 ps; choosing a smaller drive-strength buffer than the per-segment cap budget surfaces a "violation: cap budget exceeded" report (negative-path test); pytest oracles; `npm run build` clean.
- **Depends-on:** T-234, T-241, T-242

### T-253 Antenna check (process-step charge accumulation) DRC extension
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P3**
- **Scope:** extension to the T-244 DRC engine that adds the **antenna check** — a process-step-aware rule that, during photolithography + etch, exposed metal connected to a gate (and not yet connected to a diode discharge path because higher layers do not yet exist) can accumulate charge and damage the gate oxide. The rule: at each metal layer M_i, for every net that connects a poly gate to a piece of M_i but has **not yet reached a diffusion** (via M_1..M_i path), report `area(M_i_segment) / gate_oxide_area` and flag if ratio > limit (typically 400× to 2000× depending on the layer). Reuses T-244's polygon-ops + connectivity primitives. SKY130 antenna rules ship as part of the T-239 PDK install (`antenna.json`).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/drc/antenna.py` (NEW — process-step traversal + per-layer ratio check), `packages/kerf-silicon/src/kerf_silicon/drc/process_steps.py` (NEW — encodes the lithography-step ordering per PDK), `packages/kerf-silicon/src/kerf_silicon/pdk/sky130_antenna.json` (NEW — translated SKY130 antenna deck), `packages/kerf-silicon/tests/test_antenna_drc.py` (NEW), `packages/kerf-silicon/tests/fixtures/drc/antenna_violation.gds` (NEW — long M1 wire on a gate, no diffusion until M2).
- **Definition of Done:** the antenna-violation fixture reports exactly 1 antenna violation at M1 with the ratio quoted; a control fixture (same wire but with a diode added at M1) reports 0 violations; the process-step traversal correctly identifies the M1-only stage; pytest oracles; `npm run build` clean.
- **Depends-on:** T-244

### T-254 Latch-up rule checker (well-tap spacing, n+/p+ adjacency)
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** second extension to the T-244 DRC engine adding the **latch-up rule check**: in CMOS, parasitic n-p-n / p-n-p bipolars can trigger if (1) well-tap spacing exceeds the PDK limit (typically 15–25 μm) — every nwell must have a tap to VDD and every substrate region must have a tap to VSS within that distance, (2) n+ source/drain regions sit too close to p+ source/drain regions across the well boundary (typically < 0.84 μm on SKY130). Reuses T-244 polygon-ops. SKY130 latch-up rules ship as part of the T-239 PDK install (`latchup.json`).
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/drc/latchup.py` (NEW — well-tap distance + n+/p+ adjacency), `packages/kerf-silicon/src/kerf_silicon/pdk/sky130_latchup.json` (NEW — translated SKY130 latch-up deck), `packages/kerf-silicon/tests/test_latchup_drc.py` (NEW), `packages/kerf-silicon/tests/fixtures/drc/latchup_violation_tap.gds` (NEW — nwell with no tap within 20 μm), `packages/kerf-silicon/tests/fixtures/drc/latchup_violation_adjacency.gds` (NEW — n+ region 0.5 μm from p+ across nwell boundary).
- **Definition of Done:** the tap-distance fixture reports 1 violation citing the exceeded distance + the well centroid; the adjacency fixture reports 1 violation citing the offending n+/p+ pair + the measured distance; a control fixture (compliant tap spacing + ≥ 1 μm adjacency) reports 0 violations; pytest oracles; `npm run build` clean.
- **Depends-on:** T-244

### T-255 Formal equivalence checking — combinational netlist equality
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** pure-Python **formal equivalence checking** for combinational logic: take two gate-level netlists (e.g., golden pre-synthesis vs post-synthesis from T-234), build BDDs (Binary Decision Diagrams) per output net using the `pyeda` library (or our own minimal BDD if pyeda is heavy), and check `BDD(out_a) ≡ BDD(out_b)` for every primary output, generating a counter-example assignment when they differ. v1 = combinational only (cut at register boundaries — each register input + each register output is treated as a primary; the user must verify sequential correctness separately via T-249 cocotb). Pure-Python; no Yosys `equiv_make` / `equiv_simple` invocation needed.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/formal/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/formal/bdd.py` (NEW — wrap pyeda or hand-roll a small BDD), `packages/kerf-silicon/src/kerf_silicon/formal/equiv.py` (NEW — netlist → per-output BDD → BDD-equality), `packages/kerf-silicon/src/kerf_silicon/formal/counterexample.py` (NEW — extract a witness assignment on mismatch), `packages/kerf-silicon/tests/test_formal_equiv.py` (NEW), `packages/kerf-silicon/tests/fixtures/formal/half_adder_pre.json` (NEW — pre-synth netlist), `packages/kerf-silicon/tests/fixtures/formal/half_adder_post.json` (NEW — post-synth gate-level netlist), `packages/kerf-silicon/tests/fixtures/formal/half_adder_broken.json` (NEW — deliberately broken variant).
- **Definition of Done:** `equiv(half_adder_pre, half_adder_post)` returns `equivalent=True`; `equiv(half_adder_pre, half_adder_broken)` returns `equivalent=False` with a 2-bit counter-example assignment that produces different outputs; pyeda missing falls back to the in-house BDD with a clear log line; pytest oracles; `npm run build` clean.
- **Depends-on:** T-234

### T-256 Tiny Tapeout interface — TT submission packager
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** the customer-facing **Tiny Tapeout** packager: take an OpenLane-completed silicon project (T-242 outputs: `.gds`, post-route `.def`, gate-level netlist) + a `kerf.silicon.json` flow config and produce a Tiny Tapeout submission bundle. TT requires (1) `info.yaml` (project name, author, description, top-module, clock period, pin assignments), (2) Verilog source with the **exact** `tt_um_<project>` top-module name and the 24-input × 16-output TT pin protocol, (3) `commit_id` of the GDS, (4) a GHA-compatible workflow file. Wraps the T-242 outputs and emits a zip whose layout matches the current TT submission template (`github.com/TinyTapeout/tt09-template` — pinned, version-aware). Includes a `kerf silicon tt validate` CLI that lints a project against the current TT submission rules **before** zipping.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/tt/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/tt/package.py` (NEW — assembles the submission bundle), `packages/kerf-silicon/src/kerf_silicon/tt/info_yaml.py` (NEW — emits TT-compliant `info.yaml`), `packages/kerf-silicon/src/kerf_silicon/tt/wrapper.py` (NEW — wraps a user top-module into `tt_um_<project>` with the TT pin protocol), `packages/kerf-silicon/src/kerf_silicon/tt/validate.py` (NEW — pre-flight lint), `packages/kerf-cli/src/kerf_cli/commands/silicon_tt.py` (NEW — `kerf silicon tt {validate,package}`), `packages/kerf-silicon/tests/test_tt_packager.py` (NEW), `packages/kerf-silicon/tests/fixtures/tt/counter_project/` (NEW — minimal TT-shaped silicon project).
- **Definition of Done:** packaging the counter fixture produces a zip with `src/tt_um_counter.v`, `info.yaml`, and `commit_id.txt` at the expected paths; the wrapper module exposes `ui_in[7:0]`, `uo_out[7:0]`, `uio_in[7:0]`, `uio_out[7:0]`, `uio_oe[7:0]`, `ena`, `clk`, `rst_n` in exactly that order; `kerf silicon tt validate` flags a project missing the top-module rename as an error; `npm run build` clean.
- **Depends-on:** T-242

### T-257 Efabless / Caravel harness wrapping
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** the second customer-facing packager: **Efabless Caravel** harness wrapping for full MPW submissions (1 mm² user area, vs Tiny Tapeout's smaller footprint). Caravel is a more involved flow than TT — the user project sits inside a fixed `user_project_wrapper` template with a Wishbone bus + 38 GPIOs + logic-analyzer probes. This task wraps a Kerf silicon project into the Caravel `user_project_wrapper.v` shape, generates the matching `pin_order.cfg` + `openlane_config.tcl`, and emits the submission bundle. Same `validate` + `package` pattern as T-256.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/caravel/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/caravel/wrapper.py` (NEW — wraps a user design in `user_project_wrapper`), `packages/kerf-silicon/src/kerf_silicon/caravel/pin_order.py` (NEW — emits `pin_order.cfg`), `packages/kerf-silicon/src/kerf_silicon/caravel/config_tcl.py` (NEW — emits `openlane_config.tcl`), `packages/kerf-silicon/src/kerf_silicon/caravel/package.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/caravel/validate.py` (NEW), `packages/kerf-cli/src/kerf_cli/commands/silicon_caravel.py` (NEW — `kerf silicon caravel {validate,package}`), `packages/kerf-silicon/tests/test_caravel_packager.py` (NEW), `packages/kerf-silicon/tests/fixtures/caravel/counter_project/` (NEW).
- **Definition of Done:** packaging the counter fixture produces a directory matching the current `caravel_user_project` template (verified against the github.com/efabless/caravel_user_project layout pinned at a known commit); `user_project_wrapper.v` exposes the 38 GPIO bus + Wishbone master signals in the expected order; `validate` flags a project whose top-module clock domain crosses Wishbone without a synchroniser; pytest oracles; `npm run build` clean.
- **Depends-on:** T-242

### T-258 Open analog-cell library — operational amplifiers, comparators, bandgap
- **Tier:** A
- **Priority:** P3
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** an **open analog-cell library** that ships handcrafted-but-parameterised reference designs as `.sch.json` + characterised SPICE results, callable from a `.silicon.json` flow as a black-box analog block. v1 ships **3 cell families** on SKY130 only: (1) two-stage Miller-compensated **op-amp** (PMOS-input, parameterised gain-bandwidth target), (2) **strong-arm latched comparator** (clocked, parameterised offset-target), (3) **bandgap voltage reference** (Brokaw cell, parameterised IREF). Each cell ships a hand-laid `.gds` (verified LVS-clean against T-245) + a characterised `.lib`-style report (gain, BW, PSRR, offset, drift) generated by an ngspice sweep (T-236). LLM tool `instantiate_analog_cell(family, params)` returns the cell's `.gds`, schematic, and characterisation summary. Future PDK ports (GF180MCU, IHP) are deferred.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/analog/__init__.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/analog/library.py` (NEW — registry), `packages/kerf-silicon/src/kerf_silicon/analog/opamp_2stage.py` (NEW — schematic generator + characterisation oracle), `packages/kerf-silicon/src/kerf_silicon/analog/comparator_strongarm.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/analog/bandgap_brokaw.py` (NEW), `packages/kerf-silicon/src/kerf_silicon/analog/cells/opamp_2stage_sky130.gds` (NEW — hand-laid), `packages/kerf-silicon/src/kerf_silicon/analog/cells/opamp_2stage_sky130.lvs.json` (NEW — golden LVS netlist), `packages/kerf-silicon/src/kerf_silicon/analog/cells/comparator_strongarm_sky130.gds` (NEW), `packages/kerf-silicon/src/kerf_silicon/analog/cells/bandgap_brokaw_sky130.gds` (NEW), `packages/kerf-silicon/src/kerf_silicon/tools/instantiate_analog_cell.py` (NEW — LLM tool surface), `packages/kerf-silicon/tests/test_analog_library.py` (NEW).
- **Definition of Done:** `instantiate_analog_cell("opamp_2stage", {gbw_hz: 1e6})` returns a `.gds` whose LVS (T-245) reports clean against the golden schematic; `.gds` of each of the 3 cells loads in T-238's viewer; an ngspice transient on the op-amp shows the gain crosses unity within ±20 % of the requested GBW (analytic oracle for the Miller-compensated topology); pytest oracles; `npm run build` clean.
- **Depends-on:** T-236, T-237, T-238, T-239, T-245

## Firmware depth — RTOS / OTA / cross-product (T-259 … T-265)

**Strategic frame** (ROADMAP §3.5a): T-225..T-230 shipped the direct-gcc orchestrator + library registry + upload + monitor + `make_arduino_sketch`. The depth gap is the layer above: **RTOS primitives, OTA, debug, power profiling, pin-map cross-check against the kerf-electronics PCB, USB class drivers**. These are reusable building blocks the LLM composes; landing them once unlocks every per-project firmware authored thereafter. The **cross-product** payoff is T-264 specifically — the pin-map check that closes the loop between the schematic the user just routed and the firmware they're about to flash.

### T-259 Real-time scheduler primitives (FreeRTOS-equivalent abstractions, pure C library)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P1**
- **Scope:** ship a small pure-C library (`kerfrtos.h` / `kerfrtos.c`) with FreeRTOS-equivalent abstractions: `kerfrtos_task_create(fn, name, stack, priority)`, `kerfrtos_mutex_{create,take,give}`, `kerfrtos_semaphore_{create,take,give}`, `kerfrtos_queue_{create,send,receive}`, `kerfrtos_timer_{create,start,stop}`. Implementation = a thin wrapper around the platform's RTOS where one is already present (FreeRTOS on ESP32-Arduino, mbed-rtos on Cortex-M Arduino), and a minimal cooperative scheduler (single-stack round-robin) on bare-metal AVR. Goal: **one API across architectures** so an LLM-authored sketch reads the same on UNO, BluePill, and ESP32. Builds on T-227 (the build orchestrator compiles this library and links it against any project that includes `kerfrtos.h`).
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/kerfrtos.h` (NEW), `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/freertos_backend.c` (NEW — passes through to FreeRTOS), `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/mbedrtos_backend.c` (NEW), `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/cooperative_backend.c` (NEW — AVR fallback), `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/library.json` (NEW — manifest), `packages/kerf-firmware/llm_docs/kerfrtos.md` (NEW), `packages/kerf-firmware/tests/test_kerfrtos_compile.py` (NEW — compiles a 2-task fixture against each backend with subprocess-mocked gcc).
- **Definition of Done:** a 2-task fixture (LED-blink + serial-echo) compiles cleanly via T-227 against AVR (cooperative backend), ARM Cortex-M (mbed backend), and ESP32 (FreeRTOS backend); a `mutex_take` + `mutex_give` pair links to the expected backend symbol per platform (assertion on the resolved symbol in the linker map); cooperative-backend round-robin oracle: 3 tasks of equal priority execute in `A B C A B C` order; pytest oracles + a real-toolchain integration test gated on `avr-gcc` presence; `npm run build` clean.
- **Depends-on:** T-225, T-227

### T-260 Embedded LLM tool catalogue — sensors / actuators / protocols (I2C, SPI, UART, CAN, OneWire)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** an **LLM tool catalogue** for the firmware domain that mirrors the shape of `kerf-chat/llm_docs/` — small, structured, indexed by `search_kerf_docs`. Each entry is a (1) protocol-level primer (I2C / SPI / UART / CAN / 1-Wire / I2S), (2) reusable C snippet that compiles under T-227 across the 4 archs (AVR / ARM-M / xtensa / RISC-V), (3) a `make_<protocol>_driver(spec)` LLM tool. v1 ships drivers for the 12 most common parts: BME280 (I2C temp/humidity/pressure), DS18B20 (1-Wire temp), MPU6050 (I2C IMU), HX711 (SPI load cell), MCP2515 (SPI CAN), SSD1306 (I2C/SPI OLED), WS2812 (timed-bit-bang LED), MFRC522 (SPI RFID), VL53L0X (I2C ToF), DHT22 (1-Wire temp/humidity), PCA9685 (I2C PWM), MAX31855 (SPI thermocouple). Each driver lives behind a `kerfrtos`-aware API (T-259) so it works inside a task.
- **Target files/packages:** `packages/kerf-firmware/llm_docs/protocols/{i2c,spi,uart,can,onewire,i2s}.md` (NEW — primers), `packages/kerf-firmware/src/kerf_firmware/drivers/{bme280,ds18b20,mpu6050,hx711,mcp2515,ssd1306,ws2812,mfrc522,vl53l0x,dht22,pca9685,max31855}.c` + `.h` (NEW — 12 driver pairs), `packages/kerf-firmware/src/kerf_firmware/tools/make_protocol_driver.py` (NEW — `make_protocol_driver(spec)` LLM tool), `packages/kerf-firmware/llm_docs/drivers.md` (NEW — catalogue index), `packages/kerf-firmware/tests/test_drivers_compile.py` (NEW — each driver compiles via T-227 on at least one arch), `packages/kerf-firmware/tests/test_make_protocol_driver.py` (NEW).
- **Definition of Done:** all 12 drivers compile cleanly via T-227 on at least one matching arch (AVR for the simpler ones, ESP32 for the harder ones); `make_protocol_driver({protocol: 'i2c', target: 'bme280', pins: {sda: 21, scl: 22}})` emits a `.c` file that compiles + uses the expected I2C pin macros; the protocols docs are indexed by the existing `search_kerf_docs` LLM tool; pytest oracles; `npm run build` clean.
- **Depends-on:** T-227, T-259

### T-261 OTA update protocol (signed firmware over BLE/WiFi)
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** **OTA** (over-the-air) firmware update protocol: device-side library + server-side HTTP endpoint. (1) Device: `kerf_ota_check(url, current_version, public_key)` polls a manifest endpoint that returns `{version, sha256, ed25519_signature, download_url}`; verifies the signature against an embedded public key; downloads, writes to the inactive flash partition, verifies sha256, swaps the active partition, reboots. ESP32 uses esp32-ota's dual-partition layout; STM32 / SAMD use the standard "bootloader + app A + app B" three-region pattern. (2) Server: `POST /v1/ota/release` (signed by the developer's private key) registers a release; `GET /v1/ota/manifest/{device_id}` returns the device's update target. Signing key lives in the developer's local Kerf CLI (never uploaded). AVR is **out of scope** (insufficient flash for dual-partition); the device library returns the sentinel + clear "AVR is too small for OTA, consider ESP32/STM32" hint on AVR builds.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/ota/kerf_ota.h` (NEW), `packages/kerf-firmware/src/kerf_firmware/ota/esp32_backend.c` (NEW — dual-partition swap), `packages/kerf-firmware/src/kerf_firmware/ota/stm32_backend.c` (NEW — three-region swap), `packages/kerf-firmware/src/kerf_firmware/ota/samd_backend.c` (NEW), `packages/kerf-firmware/src/kerf_firmware/ota/sign.py` (NEW — local CLI signs releases with ed25519), `packages/kerf-api/src/kerf_api/routes_ota.py` (NEW — `POST /v1/ota/release` + `GET /v1/ota/manifest/{device_id}`), `packages/kerf-cli/src/kerf_cli/commands/firmware_ota.py` (NEW — `kerf firmware ota {release,keygen}`), `packages/kerf-firmware/tests/test_ota.py` (NEW), `packages/kerf-api/tests/test_routes_ota.py` (NEW).
- **Definition of Done:** device-side: a fake-flash test fixture verifies that a sha256-correct but signature-incorrect payload is **rejected** before any flash-write happens; AVR build returns the sentinel + hint; server: `POST /v1/ota/release` with an unsigned payload is rejected with HTTP 401; `GET /v1/ota/manifest/{device_id}` returns the most recent compatible release; ed25519 verification matches `nacl.signing.VerifyKey.verify` outputs for at least 3 test vectors; pytest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-227

### T-262 RTOS-aware debugger — task list / mutex inspection over JTAG/SWD
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** thin Python wrapper around **OpenOCD** + **GDB** that surfaces **RTOS-aware debug** for `kerfrtos` (T-259) and FreeRTOS targets: live task list, per-task stack-watermark, mutex / semaphore / queue state, current-task highlight. Uses OpenOCD's `mon rtos` extension where available + a `kerfrtos`-side debug hook that walks the scheduler's task table and dumps it to a known memory address on a `BKPT` trap. Surfaces in a React side-panel: tasks (name, state, priority, stack high-water), synchronisation objects (held-by, waiters), breakpoints, registers, memory view. Cloud path = sentinel ("JTAG requires the local Kerf CLI"); local CLI invokes `openocd` + `arm-none-eabi-gdb` as subprocesses.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/debug/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/debug/openocd.py` (NEW — subprocess + GDB MI/MI2 protocol bridge), `packages/kerf-firmware/src/kerf_firmware/debug/rtos_inspect.py` (NEW — walks the task table), `packages/kerf-firmware/src/kerf_firmware/runtime/kerfrtos/kerfrtos_debug_hook.c` (NEW — debug-side hook), `packages/kerf-cli/src/kerf_cli/commands/firmware_debug.py` (NEW — `kerf firmware debug attach`), `src/components/FirmwareDebugPanel.jsx` (NEW), `src/components/FirmwareDebugPanel.test.jsx` (NEW), `src/lib/firmwareDebugBridge.js` (NEW — fetch wrapper around `/firmware/debug/*` routes), `packages/kerf-firmware/tests/test_debug.py` (NEW — OpenOCD + GDB subprocess mocked).
- **Definition of Done:** with mocked openocd + gdb-mi, the debug bridge produces a structured task-list payload `[{name, state, priority, stack_high_water}, ...]`; a `mutex` reported as held-by-`task_a` produces the corresponding edge in the dependency view; stack-watermark < 10 % free triggers a warning surface in the panel; cloud-API path returns the JTAG sentinel; pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-227, T-259

### T-263 Power-profile estimation — sleep current, active current, duty-cycle estimate
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** static-analysis pass that takes a compiled firmware artefact (T-227 output) + a `power_model.json` per-board (typ. + max current per state: active, idle, light-sleep, deep-sleep, plus per-peripheral I/O cost) and produces a **power-profile estimate**: average current, expected battery life given a battery capacity, and a per-state duty-cycle breakdown. The duty-cycle estimate is derived from a coarse control-flow analysis on the disassembly (`avr-objdump` / `arm-none-eabi-objdump`) — count occurrences of sleep / wait / delay calls and rough-cycle-count between them. v1 = scope-limited (single-task sketches without complex RTOS scheduling are accurate to ±30 %; RTOS-multi-task only reports the per-task counts). The intent is "is this thing closer to a 1-day or a 1-year battery life?" not "what's the exact mA-hour."
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/power/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/power/model.py` (NEW — per-board `power_model.json` loader), `packages/kerf-firmware/src/kerf_firmware/power/disasm_analysis.py` (NEW — coarse control-flow over `objdump`), `packages/kerf-firmware/src/kerf_firmware/power/estimate.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/power/profiles/{uno,esp32,bluepill,nrf52,samd21}.json` (NEW — 5 board power models), `packages/kerf-firmware/tests/test_power_estimate.py` (NEW), `packages/kerf-firmware/tests/fixtures/power/blink_sleep_uno.elf` (NEW — known sleep-heavy fixture).
- **Definition of Done:** the blink-sleep-uno fixture reports an average current in `[0.5 mA, 5 mA]` (oracle range for an ATmega328P with periodic sleep); estimating with a 1000 mAh battery yields a life estimate of `[200 hours, 2000 hours]`; per-state breakdown reports non-zero values for `active` and `power_down`; pytest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-227

### T-264 Pin-mapping verification against the PCB (kerf-electronics + kerf-firmware cross-check)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** the **cross-product** ticket — closes the loop between the PCB designed in `kerf-electronics` (tscircuit/atopile) and the firmware authored in `kerf-firmware`. Reads the PCB's symbol-pin-to-net assignments + the firmware's `kerf.fw.json` + the firmware sources (greps for `digitalWrite(X, ...)`, `analogRead(Y, ...)`, `pinMode(Z, ...)`, etc., plus an LLM-assisted pass for less literal patterns). Cross-checks: every pin the firmware uses must exist on the board's MCU footprint; every output the firmware drives must be on a net whose load matches (LED → digital-out, motor driver → PWM-capable, ADC → analog-in); every input the firmware reads from must be on a net with a source. Reports mismatches at design-time, **before** the user compiles + flashes. v1 = Arduino-style explicit pin calls; the LLM-assisted detection of indirect pin use is offered as best-effort with a confidence score.
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/pcb_xcheck/__init__.py` (NEW), `packages/kerf-firmware/src/kerf_firmware/pcb_xcheck/pcb_pins.py` (NEW — pull pin assignments from the kerf-electronics project model), `packages/kerf-firmware/src/kerf_firmware/pcb_xcheck/fw_pins.py` (NEW — grep + LLM pass over fw sources), `packages/kerf-firmware/src/kerf_firmware/pcb_xcheck/compare.py` (NEW — produces a mismatch report), `packages/kerf-firmware/src/kerf_firmware/tools/verify_pin_mapping.py` (NEW — LLM tool `verify_pin_mapping(fw_path, pcb_path)`), `packages/kerf-firmware/tests/test_pcb_xcheck.py` (NEW), `packages/kerf-firmware/tests/fixtures/xcheck/match/{board.kicad_pcb,main.ino}` (NEW), `packages/kerf-firmware/tests/fixtures/xcheck/mismatch/{board.kicad_pcb,main.ino}` (NEW — fw uses pin 7 but board exposes 1-6 + 8-14).
- **Definition of Done:** matched fixture returns `{ok=true, missing_pins=[], wrong_load=[]}`; mismatched fixture flags `missing_pins=[7]`; running on a fixture where the firmware drives `pinMode(13, OUTPUT)` against a board where pin 13 is on an `INPUT_ONLY` net flags `wrong_load=[(13, "input-only net")]`; LLM-pass confidence < 0.6 hides the indirect-use flag (avoid false-positive noise); pytest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-230

### T-265 USB-MIDI / USB-HID / USB-CDC class drivers as reusable building blocks
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** three reusable USB class-driver building blocks for the boards that have native USB (Teensy 3.x/4.x, ESP32-S2/S3, RP2040, SAMD21/51, nRF52840, ATmega32U4): **USB-MIDI** (`kerf_usb_midi_send_note`, `kerf_usb_midi_send_cc`, callbacks for `on_note` / `on_cc`), **USB-HID** (keyboard, mouse, gamepad), **USB-CDC** (USB-as-serial). Backed by the platform's TinyUSB stack on the Arm/ESP32 boards, by `LUFA` on the ATmega32U4, and by `tinyusb` everywhere TinyUSB is supported. The Kerf-side API is identical across boards — pick the backend by the resolved board (T-225). LLM tools: `make_usb_midi_controller(spec)`, `make_usb_macro_keyboard(spec)`. AVR ATmega328P (Uno) is out of scope (no native USB).
- **Target files/packages:** `packages/kerf-firmware/src/kerf_firmware/usb/kerf_usb_midi.h` (NEW), `packages/kerf-firmware/src/kerf_firmware/usb/kerf_usb_hid.h` (NEW), `packages/kerf-firmware/src/kerf_firmware/usb/kerf_usb_cdc.h` (NEW), `packages/kerf-firmware/src/kerf_firmware/usb/backends/tinyusb_midi.c` + `_hid.c` + `_cdc.c` (NEW), `packages/kerf-firmware/src/kerf_firmware/usb/backends/lufa_midi.c` + `_hid.c` + `_cdc.c` (NEW — for ATmega32U4 Pro Micro), `packages/kerf-firmware/src/kerf_firmware/tools/make_usb_midi_controller.py` (NEW — LLM tool), `packages/kerf-firmware/src/kerf_firmware/tools/make_usb_macro_keyboard.py` (NEW), `packages/kerf-firmware/tests/test_usb_compile.py` (NEW — each class compiles via T-227 on at least one matching arch).
- **Definition of Done:** USB-MIDI compiles cleanly via T-227 against Teensy 4.0 (TinyUSB backend) + Pro Micro (LUFA backend); USB-HID `make_usb_macro_keyboard({"button_pin": 2, "send": "F13"})` emits a `.ino` that compiles + uses the expected HID keyboard report descriptor; USB-CDC echoes a known string on a mocked host (subprocess loopback via the firmware-side `setup()` writing then reading); pytest oracles; `npm run build` clean.
- **Depends-on:** T-225, T-227

## Aerospace depth follow-ups (T-266 … T-272)

**Strategic frame** (ROADMAP §3.5c): the aerospace top-10 (VLM, flutter, airfoils, 6-DOF, orbital, propulsion, composites, materials, ADCS, thermal) all shipped as P1 work in `packages/kerf-aero/`. The depth-follow-ups in this section are the items listed honestly in ROADMAP §3.5c as "tracked-but-not-yet-prioritised" — now promoted because the aerospace foundation is in place and each extension has documentable customer pull (cert paths, conceptual-design tooling, re-entry analysis). Each ticket is independently usable.

### T-266 XFOIL-class viscous solver (boundary-layer + transition) — extension to T-VLM panel
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20) — viscous-coupled solver; NACA0012 Cd 6.8%, NACA4412 Cl 4.8%, S1223 transition all within XFOIL tolerance; converges <15 iters
- **Scope:** extend the shipped 2-D linear-vortex panel solver (`packages/kerf-aero/src/kerf_aero/panel_2d.py`) to **XFOIL-class viscous coupling**: integral boundary-layer equations (laminar Falkner-Skan, turbulent Head + Green lag-entrainment), `e^N` transition prediction with N typically 9 for low-noise wind tunnels, viscous-inviscid coupling iteration to convergence, displacement-thickness feedback into the inviscid panel system. Produces airfoil polars (`Cl(α)`, `Cd(α)`, `Cm(α)`) at a target Reynolds number that match XFOIL's published results within engineering tolerance (Cl ≤ 5 %, Cd ≤ 15 %) on the canonical fixtures (NACA 0012, NACA 4412, S1223 high-lift). Goes well beyond the inviscid panel method already shipped, which is the right backbone but cannot predict separation or drag.
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/panel_2d_viscous.py` (NEW — viscous-coupled solver), `packages/kerf-aero/src/kerf_aero/boundary_layer/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/boundary_layer/laminar.py` (NEW — Falkner-Skan integral method), `packages/kerf-aero/src/kerf_aero/boundary_layer/turbulent.py` (NEW — Head + Green lag-entrainment), `packages/kerf-aero/src/kerf_aero/boundary_layer/transition_en.py` (NEW — e^N method), `packages/kerf-aero/tests/test_panel_2d_viscous.py` (NEW), `packages/kerf-aero/tests/fixtures/airfoils/xfoil_naca0012_re3e6.json` (NEW — XFOIL-published polar reference), `packages/kerf-aero/tests/fixtures/airfoils/xfoil_naca4412_re3e6.json` (NEW), `packages/kerf-aero/tests/fixtures/airfoils/xfoil_s1223_re3e5.json` (NEW).
- **Definition of Done:** NACA 0012 at Re=3e6, α=0 → Cd matches XFOIL within 15 % (oracle: ~0.0062); NACA 4412 at Re=3e6, α=4° → Cl matches XFOIL within 5 % (oracle: ~0.95); S1223 at Re=3e5 predicts a transition x/c in `[0.05, 0.20]` matching XFOIL's e^9 prediction within ±0.05; the coupled solver converges in ≤ 50 iterations for all three fixtures; pytest analytic-oracle assertions; `npm run build` clean.
- **Depends-on:** none (extends shipped panel_2d.py)

### T-267 Aircraft conceptual sizing (Raymer / Roskam weight-fraction method)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P1**
- **Scope:** **aircraft conceptual sizing** following the textbook methods of Daniel P. Raymer (*Aircraft Design: A Conceptual Approach*) and Jan Roskam (*Airplane Design*): given a mission profile (segments: warm-up, takeoff, climb, cruise, loiter, descent, land, reserves) + a payload + a target range + an airframe category (transport / fighter / GA / sailplane), iteratively converge to a sized (`W_takeoff`, `W_empty`, `W_fuel`, `S_ref`, `T/W` or `P/W`) aircraft. The weight-fraction equations are textbook + tabulated coefficients per category, so this is rule-native and very AI-native. Emits a sized-aircraft summary + a Breguet range / endurance check + a take-off-distance estimate. v1 = subsonic transport + light GA categories; supersonic / VTOL deferred.
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/sizing/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/sizing/raymer_roskam.py` (NEW — weight-fraction loop), `packages/kerf-aero/src/kerf_aero/sizing/mission.py` (NEW — segment-based mission profile), `packages/kerf-aero/src/kerf_aero/sizing/categories.py` (NEW — per-category coefficient tables), `packages/kerf-aero/src/kerf_aero/sizing/breguet.py` (NEW — range / endurance), `packages/kerf-aero/src/kerf_aero/sizing/takeoff_distance.py` (NEW), `packages/kerf-aero/src/kerf_aero/tools/size_aircraft.py` (NEW — LLM tool `size_aircraft(spec)`), `packages/kerf-aero/tests/test_sizing.py` (NEW), `packages/kerf-aero/tests/fixtures/sizing/cessna172_oracle.json` (NEW — back-of-envelope textbook oracle), `packages/kerf-aero/tests/fixtures/sizing/737_oracle.json` (NEW — Raymer Chapter-3 worked example), `packages/kerf-aero/llm_docs/sizing.md` (NEW).
- **Definition of Done:** sizing a Cessna-172-class spec (4 PAX, 800 nm range, light-GA category) converges in ≤ 30 iterations to `W_takeoff` within ±10 % of the published 2450 lb; sizing the Raymer 737-class worked example matches the chapter-3 walkthrough's `W_takeoff` within ±5 %; Breguet range with the converged `(L/D, SFC)` recovers the requested range within 2 %; pytest analytic oracles; `npm run build` clean.
- **Depends-on:** none

### T-268 Stability derivatives — Cl_α, Cn_β, Cm_α etc. from a wing+tail model
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** computation of the **stability and control derivatives** from a parametric wing + horizontal-tail + vertical-tail + fuselage geometry, using the VLM (already shipped) for the lifting-surface terms and Roskam / DATCOM closed-form expressions for the fuselage + propeller contributions. Outputs: longitudinal (`Cm_α`, `Cm_q`, `Cm_δe`, `Cl_α`, `Cl_q`, `Cl_δe`, `Cd_α`), lateral-directional (`Cl_β`, `Cl_p`, `Cl_r`, `Cn_β`, `Cn_p`, `Cn_r`, `Cn_δr`, `CY_β`, `CY_δr`), control-effectiveness (`Cm_δe`, `Cl_δa`, `Cn_δr`). Returns derivatives at a specified flight condition (Mach, altitude, α, β). Feeds directly into the shipped 6-DOF flight-dynamics module (`flight_dynamics/sixdof.py`).
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/stability/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/stability/derivatives.py` (NEW — top-level driver), `packages/kerf-aero/src/kerf_aero/stability/wing_terms.py` (NEW — uses VLM), `packages/kerf-aero/src/kerf_aero/stability/tail_terms.py` (NEW), `packages/kerf-aero/src/kerf_aero/stability/fuselage_terms.py` (NEW — DATCOM/Roskam closed-form), `packages/kerf-aero/src/kerf_aero/stability/control_surfaces.py` (NEW), `packages/kerf-aero/tests/test_stability_derivatives.py` (NEW), `packages/kerf-aero/tests/fixtures/stability/cessna172_oracle.json` (NEW — published Roskam oracle for `Cl_α` ~0.092 / deg, `Cm_α` ~−0.0125 / deg), `packages/kerf-aero/tests/fixtures/stability/f16_oracle.json` (NEW — NASA TM 80,123 reference).
- **Definition of Done:** Cessna-172 wing+tail+fuselage model returns `Cl_α` within ±10 % of the 0.092 /deg oracle; `Cm_α` returns negative (statically stable) and within ±20 % of −0.0125 /deg; F-16 model `Cn_β` matches NASA TM 80,123 within ±15 %; integration with the shipped 6-DOF solver runs without error and the converged trim returns sensible elevator angle (within ±2°); pytest analytic oracles; `npm run build` clean.
- **Depends-on:** none (uses shipped vlm.py + flight_dynamics)

### T-269 Aero-acoustics — FW-H equation for engine + propeller noise
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** **Ffowcs Williams-Hawkings (FW-H)** equation solver for far-field noise prediction from rotating sources (propeller blades, helicopter rotors, fan blades): integrate the loading-noise + thickness-noise + quadrupole-noise FW-H surface integrals over a permeable control surface, returning the acoustic pressure time-history at a list of observer locations. v1 = thickness + loading noise only (Farassat 1A formulation); quadrupole (volume) integral deferred to a follow-up. Inputs: rotating-surface mesh + per-segment force + per-segment displacement, observer locations, atmosphere (uses shipped `flight_dynamics/atmosphere.py`). Outputs: time-history pressure + OASPL (overall sound pressure level) per observer + spectrum via FFT.
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/aeroacoustics/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/aeroacoustics/fwh.py` (NEW — Farassat 1A formulation), `packages/kerf-aero/src/kerf_aero/aeroacoustics/observer.py` (NEW), `packages/kerf-aero/src/kerf_aero/aeroacoustics/oaspl.py` (NEW), `packages/kerf-aero/src/kerf_aero/aeroacoustics/spectrum.py` (NEW — FFT + band-summing), `packages/kerf-aero/tests/test_aeroacoustics.py` (NEW), `packages/kerf-aero/tests/fixtures/aeroacoustics/2bladed_propeller.json` (NEW — published reference case), `packages/kerf-aero/tests/fixtures/aeroacoustics/2bladed_propeller_expected.json` (NEW — Farassat 1A reference OASPL at known observer).
- **Definition of Done:** 2-bladed propeller at 2400 RPM at 1 m off-axis observer returns OASPL within ±3 dB of the published Farassat 1A reference; thickness-noise + loading-noise contributions correctly separable; observer directivity (sweep observer azimuth) shows the expected dipole loading-noise pattern; pytest analytic oracles; `npm run build` clean.
- **Depends-on:** none

### T-270 Heat-shield / ablation model (re-entry)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** **re-entry heat-shield / ablation** solver: 1-D transient heat conduction through a multi-layer TPS (thermal-protection-system) stack with a moving ablation front. Inputs: stack composition (e.g., PICA-X 50 mm + LI-900 backshell + Al-alloy structure), incoming heat flux time-history (typically from a re-entry trajectory simulation — uses the shipped `kerf-aero/flight_dynamics` + `orbital` modules), ablator material properties (density, specific heat, conductivity, heat of ablation, char-layer thickness rate). Outputs: surface-temperature time-history, recession-depth time-history, bondline temperature, total ablated mass. v1 = 1-D + isotropic ablator; 3-D + anisotropic char structure deferred. Reference oracles: published PICA-X stagnation-point cases from the Stardust SRC (Sample Return Capsule) literature.
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/reentry/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/reentry/ablation.py` (NEW — 1-D moving-front solver), `packages/kerf-aero/src/kerf_aero/reentry/tps_stack.py` (NEW — multi-layer stack composition), `packages/kerf-aero/src/kerf_aero/reentry/materials.py` (NEW — PICA, LI-900, AVCOAT, Carbon-Carbon, SLA-561V), `packages/kerf-aero/src/kerf_aero/reentry/heat_flux_trajectory.py` (NEW — couples to flight_dynamics), `packages/kerf-aero/tests/test_reentry_ablation.py` (NEW), `packages/kerf-aero/tests/fixtures/reentry/stardust_pica_x.json` (NEW), `packages/kerf-aero/tests/fixtures/reentry/stardust_pica_x_expected.json` (NEW — Stardust SRC published recession depth ~5 mm).
- **Definition of Done:** Stardust SRC stagnation-point fixture returns peak surface-temp within ±10 % of the published 2700 K; total recession-depth matches the published ~5 mm within ±20 %; bondline temperature stays below 250 °C (the structural limit) — a clear safety-margin oracle; 1-D conduction matches an analytic constant-flux semi-infinite-slab solution at t=10 s without ablation; pytest analytic + reference oracles; `npm run build` clean.
- **Depends-on:** none (uses shipped flight_dynamics for the trajectory)

### T-271 Aerospace fasteners catalogue (Hi-Lok, Cherry, NAS/MS/AS standards)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P1**
- **Scope:** an **aerospace-fasteners catalogue** in the partsgen pattern (T-228..T-230 of the partsgen track) following NAS / MS / AS / NASM standards. v1 covers 6 families: (1) **Hi-Lok HL18 / HL19** (titanium pin + collar, the most-common aerospace blind-bolt), (2) **Cherry CR2249** (blind rivet, sheet-metal joining), (3) **MS27039** (pan-head machine screw, structural), (4) **NAS6603..6604** (hex-head close-tolerance, structural), (5) **AN960** (washer), (6) **MS21042** (hex self-locking nut). Each family is a parametric generator that emits a `.feature` body matching the standard's dimensional tables (NAS / MS dimensions are published + tabulated). LLM tool `instantiate_aero_fastener(standard, callout)` (e.g., `("HL18", "PB-6-8")`).
- **Target files/packages:** `packages/kerf-partsgen/src/kerf_partsgen/aerospace/__init__.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/hilok.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/cherry_rivet.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/ms27039.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/nas66xx.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/an960.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/ms21042.py` (NEW), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/tables/{hilok,cherry,ms27039,nas66xx,an960,ms21042}.json` (NEW — dimensional tables per standard), `packages/kerf-partsgen/src/kerf_partsgen/aerospace/instantiate.py` (NEW — `instantiate_aero_fastener` LLM tool), `packages/kerf-partsgen/tests/test_aero_fasteners.py` (NEW).
- **Definition of Done:** `instantiate_aero_fastener("HL18", "PB-6-8")` returns a Body whose pin diameter is 6/16 in within tolerance + grip length 8/16 in; an MS27039 #10-32 generates with the expected major diameter 0.190 in ± 0.005; all 6 generators emit `validate_body`-clean Bodies; dimensional tables cover ≥ 10 callouts per family; pytest oracles; `npm run build` clean.
- **Depends-on:** none

### T-272 DO-178C / DO-254 certification artefact templates
- **Tier:** A
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-18) · **Tier A · P2**
- **Scope:** **certification artefact templates** for the two aerospace cert standards: **DO-178C** (airborne software — covers any firmware written in kerf-firmware that flies, e.g., the autopilot loop) and **DO-254** (airborne hardware — covers any FPGA / ASIC, including our T-256/T-257 silicon submissions). Each ships (a) the required-artefact list per DAL level (A through E), (b) markdown templates for the must-deliver documents (Plan for Software Aspects of Certification / Software Development Plan / Software Verification Plan, PHAC / Hardware Development Plan / Hardware Verification Plan, conformity), (c) requirements-traceability matrix scaffolding (`.req.json` ↔ `.test.json`), (d) a generator that takes a project + a target DAL and emits a starter cert package the user can fill in. **Templates only** — we do not claim to do the cert ourselves; we lower the activation energy. The market-fit here is the unique aerospace + firmware + silicon combination: no other tool sits across all three flows simultaneously.
- **Target files/packages:** `packages/kerf-aero/src/kerf_aero/cert/__init__.py` (NEW), `packages/kerf-aero/src/kerf_aero/cert/do178c.py` (NEW), `packages/kerf-aero/src/kerf_aero/cert/do254.py` (NEW), `packages/kerf-aero/src/kerf_aero/cert/templates/do178c/{psac,sdp,svp,scmp,sqap,sas}.md` (NEW — 6 DO-178C document templates), `packages/kerf-aero/src/kerf_aero/cert/templates/do254/{phac,hdp,hvp,hcmp}.md` (NEW — 4 DO-254 document templates), `packages/kerf-aero/src/kerf_aero/cert/traceability.py` (NEW — requirements-↔-test matrix scaffolding), `packages/kerf-aero/src/kerf_aero/cert/dal_artefacts.py` (NEW — required-artefact list per DAL A..E), `packages/kerf-aero/src/kerf_aero/tools/generate_cert_package.py` (NEW — LLM tool `generate_cert_package(project, standard, dal)`), `packages/kerf-aero/llm_docs/cert.md` (NEW — user-facing primer), `packages/kerf-aero/tests/test_cert_templates.py` (NEW).
- **Definition of Done:** `generate_cert_package(project, "DO-178C", "DAL-B")` emits 6 markdown files at the expected paths with the project name + DAL substituted into the templates; the DAL-B artefact list contains ≥ 20 required artefacts; the traceability matrix scaffolding emits a `.req.json` + matching `.test.json` skeleton with non-empty IDs; the DO-254 path generates the analogous package for the silicon DAL-B level; pytest oracles; `npm run build` clean.
- **Depends-on:** none

## Frontend integration debt — wire up shipped backends (T-273 … T-280)

**Strategic frame** (ROADMAP §3.5d): T-225..T-248 + the aerospace top-10 shipped fast enough that the frontend has not yet caught up. None of this is new capability; it is wire-up that converts shipped Python packages into "an evaluator can click it" UI surfaces. Sequenced ahead of new sector work because a shipped capability no user can reach pays no credibility dividend.

### T-273 Wire kerf-silicon outputs into existing LayoutViewer (real GDS upload → SKY130-coloured render)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** wire the shipped `LayoutViewer.jsx` (T-238) to a real backend HTTP endpoint that accepts an uploaded `.gds` file, parses it via T-237's reader, applies T-239's SKY130 layer-colour palette via the T-239 `layers.json`, and streams the parsed shapes to the frontend as JSON-polygons. Today the LayoutViewer renders test fixtures only; this ticket closes the gap so a user can `Upload → kerf inverter.gds → render with SKY130 colours`. Adds a new file kind `gds_layout` route handler that opens the viewer when a `.gds` is double-clicked in the file tree.
- **Target files/packages:** `packages/kerf-silicon/src/kerf_silicon/routes_layout.py` (edit — accept multipart upload + parse via T-237 + serialise to JSON), `packages/kerf-silicon/tests/test_routes_layout.py` (edit — assert SKY130-coloured output), `src/components/LayoutViewer.jsx` (edit — wire `/silicon/layout/parse` POST + render with the PDK-coloured layer-map from T-239), `src/lib/gdsLoader.js` (edit — fetch the parsed payload from the new backend route), `src/components/LayoutViewer.test.jsx` (edit — vitest with mocked fetch returning the SKY130 palette), `src/routes/Editor.jsx` (edit — when a file is `kind=gds_layout` open the LayoutViewer instead of the text editor), `src/components/FileTree.jsx` (edit — `.gds` icon).
- **Definition of Done:** uploading the SKY130 inverter fixture (existing in `packages/kerf-silicon/tests/fixtures/gds/inverter_sky130.gds`) renders ≥ 1 visible polygon per layer with the SKY130 layer-colour palette applied (verified via a vitest snapshot of the layer-colour dict the canvas receives); double-clicking a `.gds` in the file tree opens the LayoutViewer (not the text editor); pytest + vitest oracles; `npm run build` clean.
- **Depends-on:** T-237, T-238, T-239, T-248

### T-274 Wire kerf-firmware build pipeline into project file tree (Build / Upload / Monitor buttons)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** wire T-227 + T-228 + T-229 into a single project-level firmware panel: **Build** button runs `kerf_firmware.orchestrator.compile` and streams the build log to a console panel, **Upload** button (CLI-only — gated on a local-CLI heartbeat) runs the T-228 wrapper, **Monitor** opens the T-229 WebSerial panel. The trigger is a right-rail panel that appears when the project contains a `kerf.fw.json`. Build artefacts (`.elf` / `.hex` / `.bin`) land in `.kerf-fw/build/<env>/` and are visible in a sub-section of the file tree, downloadable via a sign-back-then-download flow. Cloud path shows the existing "this requires the local Kerf CLI" sentinel for Upload + Monitor; Build is server-runnable.
- **Target files/packages:** `src/components/FirmwarePanel.jsx` (NEW — Build / Upload / Monitor toolbar), `src/components/FirmwarePanel.test.jsx` (NEW), `src/components/FirmwareBuildConsole.jsx` (NEW — streaming-log panel), `src/lib/firmwareBuildBridge.js` (NEW — fetch wrapper around `/firmware/build/start` + EventSource for the streaming log), `packages/kerf-firmware/src/kerf_firmware/routes_build.py` (NEW — `POST /firmware/build/start` + `GET /firmware/build/{id}/log` SSE stream), `packages/kerf-firmware/tests/test_routes_build.py` (NEW), `src/components/FileTree.jsx` (edit — render `.kerf-fw/` artefacts sub-tree), `src/routes/Editor.jsx` (edit — show the FirmwarePanel when `kerf.fw.json` is present).
- **Definition of Done:** opening a project containing `kerf.fw.json` reveals the FirmwarePanel; clicking Build calls `/firmware/build/start` and the log streams via SSE to the console; build success surfaces the `.hex` in the file tree under `.kerf-fw/build/<env>/`; Upload + Monitor on cloud return the CLI-only sentinel; vitest mocks both the fetch and EventSource and asserts the streaming-log lines render; pytest oracles; `npm run build` clean.
- **Depends-on:** T-227, T-228, T-229, T-230, T-248

### T-275 Comparison-page matrix expansion — add silicon (vs Cadence/Synopsys), firmware (vs PlatformIO/Arduino IDE), aerospace (vs ANSYS Fluent/STK)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** extend the existing comparison hub (`src/routes/compare/`) with three new feature-matrix categories that surface the §3.5a / §3.5b / §3.5c work to evaluators: **Silicon / EDA** (vs Cadence Virtuoso, Synopsys Design Compiler, Mentor Calibre, KLayout, OpenLane standalone), **Firmware** (vs PlatformIO, Arduino IDE, Espressif IDF, STM32CubeIDE), **Aerospace** (vs ANSYS Fluent, AGI STK, MATLAB Aerospace Toolbox, XFOIL, OpenVSP). Each gets its own `CategoryMatrix` instance with rows for the headline capabilities + colour-coded cells per tool. Also adds per-tool comparison routes (`/compare/cadence`, `/compare/synopsys`, `/compare/platformio`, `/compare/arduino-ide`, `/compare/ansys-fluent`, `/compare/agi-stk`, `/compare/xfoil`) following the existing route shape.
- **Target files/packages:** `src/routes/compare/index.jsx` (edit — add 3 categories), `src/routes/compare/CategoryMatrix.jsx` (edit if needed for new column shapes), `src/routes/compare/CompareCadence.jsx` (NEW), `src/routes/compare/CompareSynopsys.jsx` (NEW), `src/routes/compare/CompareKlayout.jsx` (NEW), `src/routes/compare/CompareOpenLane.jsx` (NEW), `src/routes/compare/ComparePlatformio.jsx` (NEW), `src/routes/compare/CompareArduinoIde.jsx` (NEW), `src/routes/compare/CompareStm32cube.jsx` (NEW), `src/routes/compare/CompareAnsysFluent.jsx` (NEW), `src/routes/compare/CompareAgiStk.jsx` (NEW), `src/routes/compare/CompareXfoil.jsx` (NEW), `src/routes/compare/CompareOpenvsp.jsx` (NEW), `src/App.jsx` (edit — register the new routes), `src/routes/compare/__tests__/compareCategories.test.jsx` (NEW — assert all three new matrices render with ≥ 5 rows each).
- **Definition of Done:** `/compare` shows three new categories (Silicon / EDA, Firmware, Aerospace) with ≥ 5 feature rows each; clicking a cell navigates to the matching per-tool page; each per-tool page renders without error; vitest snapshot on the 3 new matrix shapes; `npm run build` clean.
- **Depends-on:** T-225..T-248, aerospace top-10 (shipped)

### T-276 Domains pages — add /silicon, /firmware, /aerospace landing routes
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add three new domain landing routes following the existing `src/routes/domains/` pattern (`Electronics.jsx` + `electronics.meta.js`, etc.): **Silicon** (`/silicon` — RTL → GDS-II story, Tiny Tapeout funnel, Phase 1+2+3 capability matrix, link to the LayoutViewer demo), **Firmware** (`/firmware` — direct-gcc + library registry story, `make_arduino_sketch` demo embed, board catalogue, link to the FirmwarePanel demo), **Aerospace** (`/aerospace` — VLM / flutter / orbital / propulsion / ADCS story with a wing-polar demo embed). Each page follows the `DomainPage.jsx` shell with a meta module for the SEO + sidebar entry. Registered in `index.jsx` so they appear in the existing domain index list.
- **Target files/packages:** `src/routes/domains/Silicon.jsx` (NEW), `src/routes/domains/silicon.meta.js` (NEW), `src/routes/domains/Firmware.jsx` (NEW), `src/routes/domains/firmware.meta.js` (NEW), `src/routes/domains/Aerospace.jsx` (NEW), `src/routes/domains/aerospace.meta.js` (NEW), `src/routes/domains/index.jsx` (edit — register the 3 new entries), `src/App.jsx` (edit — register `/silicon`, `/firmware`, `/aerospace` routes), `src/routes/domains/__tests__/newDomains.test.jsx` (NEW — assert all three render with the meta title + main copy).
- **Definition of Done:** `/silicon` / `/firmware` / `/aerospace` each render with a hero, capability list, and at least one demo embed (LayoutViewer / FirmwarePanel / wing-polar plot); they appear in the existing domains index; meta titles are SEO-correct; vitest snapshot on each; `npm run build` clean.
- **Depends-on:** none (depends on shipped backends only)

### T-277 Docs-viewer LLM consolidation — index the new package docs (kerf-silicon, kerf-firmware, kerf-aero)
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** index the LLM docs that already exist in the three new packages (`packages/kerf-silicon/llm_docs/`, `packages/kerf-firmware/llm_docs/`, `packages/kerf-aero/llm_docs/`) into the **docs-viewer manifest** + the **`search_kerf_docs` LLM tool**. The `scripts/build-docs-manifest.mjs` walks `packages/*/llm_docs/**.md` already; this ticket ensures the new packages' docs are surfaced under the correct sidebar group (probably "Domains" with new sub-groups Silicon / Firmware / Aerospace), and that `search_kerf_docs` returns hits from them. Adds a new "Domains → Silicon / Firmware / Aerospace" sub-section in the sidebar taxonomy. Also adds a placeholder `domain.md` per package where one isn't already present so the sidebar entry has a stable landing target.
- **Target files/packages:** `scripts/build-docs-manifest.mjs` (edit — add the 3 sub-group entries to the taxonomy), `packages/kerf-silicon/llm_docs/domain.md` (NEW or edit — sector primer), `packages/kerf-firmware/llm_docs/domain.md` (NEW or edit), `packages/kerf-aero/llm_docs/domain.md` (NEW or edit), `packages/kerf-chat/src/kerf_chat/tools/search_kerf_docs.py` (edit — ensure the search index includes the 3 packages), `packages/kerf-chat/tests/test_search_kerf_docs.py` (edit — assert hits for "GDS-II", "kerf.fw.json", "vortex-lattice"), `public/docs-manifest.json` (regenerated artefact — check in the rebuild).
- **Definition of Done:** the docs viewer sidebar shows Domains → Silicon / Firmware / Aerospace with at least 2 entries each; `search_kerf_docs("GDS-II")` returns the T-237 docs as a top hit; `search_kerf_docs("kerf.fw.json")` returns T-230; `search_kerf_docs("vortex-lattice")` returns the kerf-aero docs; `public/docs-manifest.json` round-trips clean through the build script; pytest + manifest-build oracles; `npm run build` clean.
- **Depends-on:** none (docs already exist; this is indexer + sidebar wiring)

### T-278 New-file dialog — surface `.vhd`/`.v`/`.sv`/`.gds`/`.lef`/`.lib`/`.spice`/`.fw.json`/`.ato`/`.ino` as first-class types
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** the new-file dialog today surfaces a hand-curated set of kinds; this ticket adds the **silicon / firmware** extensions as first-class entries with icons + starter content. New entries: VHDL (`.vhd`), Verilog / SystemVerilog (`.v` / `.sv`), GDS-II layout (`.gds` — read-only opens the LayoutViewer), LEF (`.lef`), Liberty (`.lib`), SPICE netlist (`.spice` / `.cir`), Firmware project manifest (`kerf.fw.json`), Atopile circuit (`.ato`), Arduino sketch (`.ino`). Each gets a starter-content template (an empty `entity` block for VHDL, an empty `module` block for Verilog, the documented JSON skeleton for `kerf.fw.json`, etc.). Reuses T-248's file-kind enum so the resulting file lands in the correct kind.
- **Target files/packages:** `src/components/NewFileDialog.jsx` (edit — add the new entries), `src/components/NewFileDialog.test.jsx` (edit — assert all 10 new entries are clickable and create the right file kind), `src/lib/newFileTemplates.js` (NEW — single source of starter-content per kind), `src/lib/newFileTemplates.test.js` (NEW — vitest on the templates), `src/__tests__/newFileDialog.test.js` (edit — extend the existing dropdown contract test), `packages/kerf-api/src/kerf_api/routes_files.py` (edit if needed — accept the new kinds on create).
- **Definition of Done:** the New-file dialog lists all 10 new entries with the correct icon + starter content; creating "New VHDL file" generates `untitled.vhd` of kind `hdl_vhdl` with the empty-entity starter; creating "New Firmware project" generates `kerf.fw.json` with the documented skeleton; `.gds` opens in the LayoutViewer not the text editor; vitest + pytest oracles; `npm run build` clean.
- **Depends-on:** T-248

### T-279 Landing page — add silicon + firmware + aerospace as new sector cards
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add three new sector cards to the landing page (`src/routes/Landing.jsx`) matching the visual language of the existing Mechanical / Electronics / BIM / Jewelry / Civil cards: **Silicon** (icon: chip; tagline: "Chat-driven RTL to GDS-II"; CTA: `/silicon`), **Firmware** (icon: cpu / microcontroller; tagline: "Direct-gcc + library registry, no `pio` runtime"; CTA: `/firmware`), **Aerospace** (icon: airplane; tagline: "VLM, flutter, orbital mechanics, ADCS, in one project"; CTA: `/aerospace`). Each card mirrors the existing pattern (image + headline + 1-line value-prop + CTA button). Cards are tested via the existing landing-page vitest.
- **Target files/packages:** `src/routes/Landing.jsx` (edit — append 3 new sector cards in the existing sector grid), `src/routes/__tests__/Landing.test.jsx` (edit — assert the 3 new cards appear), `src/assets/sectors/silicon.svg` (NEW — illustrative SVG, in the style of the existing sector illustrations), `src/assets/sectors/firmware.svg` (NEW), `src/assets/sectors/aerospace.svg` (NEW).
- **Definition of Done:** landing page renders 3 new sector cards in the grid; each card's CTA links to the correct domain route (T-276 routes); the cards' SVGs scale clean at 1×/2× DPR; vitest asserts the 3 cards' headlines + CTAs; `npm run build` clean.
- **Depends-on:** T-276

### T-280 Search / command-palette — index file-kinds + package docs so Cmd-K finds silicon/firmware tooling
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped
- **Scope:** add a global **Cmd-K command palette** that indexes (1) every file-kind from T-248's enum so `Cmd-K` → `vhdl` shows "Create new VHDL file" (open the new-file flow from T-278) + "Open existing .vhd files in this project", (2) every `llm_docs/*.md` entry from T-277's manifest so `Cmd-K` → `GDS-II` jumps to the docs page, (3) the existing app-level routes (`/silicon`, `/firmware`, `/aerospace`, `/compare`, every `/compare/*`, `/docs`, `/projects`, `/library`, `/pricing`, etc.). The palette is a lightweight in-house React component (no `cmdk` dep — Kerf already has React + tailwind, and matching the existing design language is the win). Keyboard: `Cmd-K` (mac) / `Ctrl-K` (win/linux) opens; fuzzy match on the displayed title; `Enter` activates the selected entry; `Escape` closes.
- **Target files/packages:** `src/components/CommandPalette.jsx` (NEW), `src/components/CommandPalette.test.jsx` (NEW — vitest with mocked manifest + keyboard events), `src/lib/commandPaletteIndex.js` (NEW — builds the indexed entries from the docs manifest + the file-kinds enum + the route table), `src/lib/commandPaletteIndex.test.js` (NEW — vitest on the index builder), `src/lib/fuzzyMatch.js` (NEW — small fuzzy-match helper, ranked scoring), `src/lib/fuzzyMatch.test.js` (NEW), `src/App.jsx` (edit — mount the CommandPalette globally + the Cmd-K keydown listener), `src/components/Header.jsx` (edit — surface a small "Cmd-K" affordance in the top bar so users know it exists).
- **Definition of Done:** pressing `Cmd-K` opens the palette over any route; typing `vhdl` ranks "Create new VHDL file" first; typing `gds` ranks "Open LayoutViewer" or the GDS-II docs page in the top 3; typing `roadmap` jumps to `/roadmap`; the palette closes on `Escape`; the fuzzy-match scoring oracle: a single-char typo (`/sliicon` vs `silicon`) still ranks the correct entry in the top 3; vitest oracles on the index builder + the fuzzy scorer + the keyboard handler; `npm run build` clean.
- **Depends-on:** T-248, T-277, T-278

## Textiles / Fashion / Soft-goods (T-281 … T-286)

User-direction 2026-05-19. Extends T-179 (apparel pattern-making) with deeper textile-specific tooling: woven/knit pattern generators, drape simulation, dye-sublimation art alignment, cut-room nesting at production scale, smart-textile / e-textile integration.

### T-281 Textile weave + knit pattern generators
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** parametric generators for textile structures — plain weave, twill (2/1 right-hand, etc.), satin, jacquard pattern from a draft; knit structures jersey/rib/interlock with tuck/miss/loop stitches; full draft + treadle + tie-up notation. Pure-Python; outputs both vector geometry + a tile-able raster for previews.
- **Target files/packages:** `packages/kerf-textiles/` (NEW package — pyproject.toml, src/kerf_textiles/{weave,knit,draft,export}.py, tests, llm_docs).
- **Definition of Done:** plain-weave float-length analysis matches the analytic formula; 2/1 twill produces the canonical diagonal stagger; jersey-knit stitch density matches `gauge·courses` to 1%; draft notation round-trips through writer/reader; pytest analytic oracles.
- **Depends-on:** none

### T-282 Drape / cloth-simulation seed
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** mass-spring cloth model on a textile mesh; gravity + air drag + collision against a body or table; uses kerf-motion's RK4 integrator (T-163). Settle to static drape under gravity for visualisation; export the draped mesh as STEP / glTF for rendering.
- **Target files/packages:** `packages/kerf-textiles/src/kerf_textiles/drape.py`, `packages/kerf-textiles/src/kerf_textiles/mass_spring.py`, tests with analytic oracles (a square cloth pinned at 2 corners droops with a catenary shape — verify max-sag formula).
- **Definition of Done:** catenary droop matches analytic to 5%; cloth settles to static within N steps; pytest analytic oracles.
- **Depends-on:** T-163 (kerf-motion RK4 integrator)

### T-283 Dye-sublimation + screen-print art alignment
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** take a 3D garment + a 2D artwork file, produce the pre-distorted print-ready file with bleed + registration marks for dye-sub (continuous tone) or screen-print (spot colour separation). Mesh-unwrap the garment, project the artwork, output PNG/PDF per panel.
- **Target files/packages:** `packages/kerf-textiles/src/kerf_textiles/sublimation.py`, `packages/kerf-textiles/src/kerf_textiles/screen_print.py`, tests.
- **Definition of Done:** unwrap a cylinder→PNG round-trip preserves area to 1%; bleed margin is the expected width; pytest.
- **Depends-on:** T-281

### T-284 Production-scale cut-room nesting
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** extends T-179's marker-making with production-grade No-Fit-Polygon nesting on multiple fabric rolls of varying widths; supports grain-line constraints + ply-direction. Reuses kerf-cad-core.nesting if available; otherwise pure-Python NFP.
- **Target files/packages:** `packages/kerf-textiles/src/kerf_textiles/cut_room.py`, tests.
- **Definition of Done:** marker utilisation on a known input ≥ 80%; grain-line constraint honoured; pytest oracles.
- **Depends-on:** T-179

### T-285 E-textile / smart-textile design
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** integrate conductive thread routing on a garment pattern; pair with kerf-electronics PCB design for the rigid controller + flex transition. Resistance + heating calc for resistive yarns; LED-fabric layout (Adafruit Flora-class).
- **Target files/packages:** `packages/kerf-textiles/src/kerf_textiles/etextiles.py`, tests.
- **Definition of Done:** resistive heating calc matches I²R to 1%; LED-fabric layout has correct serial+parallel current; pytest.
- **Depends-on:** T-281, T-191 (tscircuit ratsnest)

### T-286 Textile material catalogue + sustainability metrics
- **Tier:** B
- **Priority:** P2
- **Status:** ✅ shipped (2026-05-20)
- **Scope:** curated catalogue of 50+ textile materials: cotton (organic/conventional), polyester (virgin/recycled), wool, silk, linen, viscose, lyocell, nylon, hemp, leather (full-grain/PU). Each entry: density (g/m²), tensile strength, elongation, water consumption (L/kg), CO₂ footprint (kg CO₂e/kg), biodegradability, certifications (GOTS, OEKO-TEX, Bluesign).
- **Target files/packages:** `packages/kerf-textiles/src/kerf_textiles/materials.py`, `packages/kerf-textiles/src/kerf_textiles/sustainability.py`, tests.
- **Definition of Done:** 50+ entries; lookup by category; LCA sustainability score for a garment from its material mix; pytest oracles.
- **Depends-on:** none

## Viewport performance (T-320)

### T-320 Large-assembly LOD + lazy-load + perf harness
- **Tier:** A
- **Priority:** P0
- **Status:** ✅ shipped (2026-05-20) · **Tier A · P0**
- **Scope:** Angular-size LOD pipeline (`src/lib/lod.js`), frustum-cull + prefetch lazy-load manager (`src/lib/assemblyLoader.js`), quadric-edge-collapse decimation thin wrapper (`packages/kerf-cad-core/src/kerf_cad_core/mesh_decimate.py`), Python perf harness for N ∈ {100,1k,5k,10k} (`scripts/perf_assembly.py`), pytest + vitest oracle suite.
- **Target files/packages:**
  - `src/lib/lod.js` — LOD pipeline (angular-size threshold + QEM decimation)
  - `src/lib/assemblyLoader.js` — lazy-load: frustum-cull + N-component prefetch window
  - `packages/kerf-cad-core/src/kerf_cad_core/mesh_decimate.py` — `decimate_to_ratio` QEM wrapper
  - `scripts/perf_assembly.py` — perf harness: parse+LOD-select at 4 scales; modelled FPS (no GPU)
  - `tests/perf/test_large_assembly.py` — pytest: mesh_decimate ~10% reduction + bbox; frustum/prefetch; LOD selection; harness at all scales
  - `src/lib/lod.test.js` — vitest: decimation, buildLODProxy, angularSize, selectLOD
  - `src/lib/assemblyLoader.test.js` — vitest: frustum-cull, prefetch, eviction, factory
- **Definition of Done:**
  - VERIFIED (headless): mesh_decimate ~10% triangle reduction + bbox preservation; frustum-cull + prefetch (parts outside frustum+window not loaded); LOD proxy swap below angular-size threshold; perf harness runs at {100,1k,5k,10k}; pytest 29 passed; vitest 38 passed; `npm run build` clean.
  - MODELLED (no GPU): fps_proxy / fps_full estimated from 500 Mtri/s budget + 0.03 ms/draw-call overhead — documented in `scripts/perf_assembly.py`.
- **Depends-on:** T-15, T-16

## Kernel Phase 4 — SubD depth + interop (T-340)

### T-340 Kernel Phase 4 — SubD modeling depth + parametric wizards + interop
- **Tier:** A
- **Priority:** P0
- **Status:** 🟡 in progress (2026-05-21) — Phase 4 (GK-73..GK-93) COMPLETE; Phase 5 (GK-94..GK-133, 40 items) opened: Class-A analysis, curve/surface utilities, SubD depth, mesh+implicit (SDF/marching-cubes), lattice/TPMS generative, mould tooling, assembly mates/interference, DXF/PLY/3DM interop, gears/threads/springs, feature recognition
- **Scope:** 21 GK items (GK-73..GK-93) covering Blender-style SubD authoring depth (inset face, bridge loops, loop slide, knife), parametric wizards every CAD ships (hole, helical sweep, n-rail sweep, pattern), robustness ops for imported geometry (body simplify/heal, split, replace face, imprint), printability analysis (wall-thickness map, draft analysis, symmetry detection), sheet metal bend/unfold, and round-trip mesh I/O (3MF, glTF/GLB, OBJ, STL reader). Listed in `docs/plans/geometry-kernel-roadmap.md` §4b. **Priority order is the listing order** — top-9 (GK-73..GK-81) are highest user-value × smallest effort, sonnet-parallel; later items unlock harder workflows. All pure-Python, additive to the public façade.
- **Target files/packages:** see per-item `geom/<file>.py` references in roadmap §4b; tests live in `packages/kerf-cad-core/tests/`. Public exports added to `geom/__init__.py`.
- **Definition of Done:**
  - All 21 GK-73..GK-93 entries ticked in `docs/plans/geometry-kernel-roadmap.md` with `*Landed: N tests.*`
  - `python -m pytest packages/kerf-cad-core/tests/ -q` green
  - `geom/__init__.py` exports each new public symbol; import-snapshot test passes
  - `npm run build` clean
- **Depends-on:** GK-01..GK-72 (all kernel spine + long-tail) — complete

---

## Infrastructure migration — Fly.io → Koyeb (T-400 … T-410)

ROADMAP § 7.1 ("Hosted infrastructure"). Fly.io discontinued GPU
instances, blocking the Cycles render epic (and any future GPU-accel
work). Koyeb sells the full GPU ladder (RTX-A4000 → H100) in Frankfurt,
Washington and Singapore with per-second billing and the same Docker
deploy model. All tasks are P0; the order is the order they should ship.

### T-400 Ground GPU billing rates to Koyeb actuals
- **Tier:** A
- **Priority:** P0
- **Status:** 🚧 in flight (2026-05-24)
- **Scope:** Replace the placeholder Modal-tier numbers in `kerf-render.pricing_meter` with the real Koyeb hourly rates. Add SKUs for the full Koyeb ladder (rtx_a4000, l4, a6000, l40s, a100, a100_sxm, h100, h200) converted to USD/GPU-second. Lift `GPU_MARKUP_PCT` from 20% → 35% to absorb per-second billing variance + storage egress + autoscale buffer. Make `l4` the default (replaces `a10g`, similar 24GB tier).
- **Target files:** `packages/kerf-render/src/kerf_render/pricing_meter.py`, `packages/kerf-render/tests/test_pricing_meter.py`, `packages/kerf-billing/src/kerf_billing/render_meter.py` (default-rate lookup), `packages/kerf-pricing/llm_docs/pricing.md`.
- **Definition of Done:**
  - GPU rate table grounded to live Koyeb pricing with provider URL cited in the docstring
  - Tests assert the new defaults and ladder values exactly
  - User-facing render-cost docs reflect Option-C hybrid (~2-3× drop in user price vs old Modal-tier rates)
  - `pytest packages/kerf-render packages/kerf-billing packages/kerf-pricing -q` green

### T-401 Billing-hole audit fan-out
- **Tier:** A
- **Priority:** P0
- **Status:** ✅ shipped (2026-05-24) — report at [`docs/audits/billing-holes-2026-05-24.md`](docs/audits/billing-holes-2026-05-24.md). 6× P0, 9× P1, 7× P2 holes found. Headline: GPU renders and storage growth are both $0-revenue today because the meter calls are dead code and `user_id` is NULL in `render_jobs`. T-402 follow-ups required before Koyeb cutover.
- **Scope:** Sonnet-agent fan-out (3 parallel, isolated worktrees) to find revenue leaks before we cut over. Each agent reads a slice of the billing surface and reports findings as a short markdown table — no code changes from the audit agents; this task is research only.
  - **Agent 1 — spend paths:** every place chat/render/storage/compute COGS is incurred. Find paths that mutate state but DON'T call `kerf_billing.spend.commit_spend` / `cloud_debit_balance` / `render_meter.meter_render_job`.
  - **Agent 2 — quota & abuse vectors:** `kerf_free` bucket bypass paths, retry storms, rate-limit gaps, free-tier loops, cheap-tier model masquerading.
  - **Agent 3 — egress, storage, and BYO leaks:** unbilled outbound bandwidth, untracked storage growth, BYO-key paths that still hit our LLM keys.
- **Target files:** read-only across `packages/kerf-billing/`, `packages/kerf-pricing/`, `packages/kerf-render/`, `packages/kerf-cloud/billing*`, `packages/kerf-api/`. Output: `docs/audits/billing-holes-2026-05-24.md` (a single consolidated report).
- **Definition of Done:**
  - Report exists with a prioritised P0/P1/P2 list of holes
  - Each finding cites file:line, the leak vector, and the proposed fix shape
  - Holes flagged P0 spawn T-402 follow-ups before cutover

### T-402 Plug P0 holes from T-401
- **Tier:** A
- **Priority:** P0
- **Status:** ✅ shipped (2026-05-24) — all 6 P0 holes plugged via 4 parallel Sonnet worktree agents, integrated by SHA: R4 (`0d5f0682`), R3 (`0eb5ea4b`), R1+R2+R8 (`f6d35c85`), R5+R6 (`b70cc6eb`), test-fixture integration patch (`573cd8b2`). Full scoped pytest suite back to the 10-failure pre-existing baseline (file_kinds, OTA inter-test pollution, byo_blender Docker — none caused by these fixes). JS suite: 9534/9534 green.
- **Scope:** Plug the 6 P0 holes from [the audit](docs/audits/billing-holes-2026-05-24.md), grouped to minimise PR count:
  1. **R1 + R2 + R8** — `kerf-render/queue_worker.py` calls `meter_render_job` after `mark_complete`; `_enqueue_render` threads `user_id` into the INSERT; `record_storage` helper added to `kerf_core.db.queries.usage_events`. Single PR, unblocks GPU + storage revenue together.
  2. **R3** — register a `StorageBillingWorker` (or extend `BillingResetWorker`) to fire `monthly_storage_debit()` on a monthly tick with an idempotency guard.
  3. **R5 + R6** — close the render-gate bypass: reuse the verified `user_id` inside `_run_billing_gate`, and pass an internal auth token from `_generate_project_cover`'s `httpx` call.
  4. **R4** — unify the Gemini provider key across `kerf_chat` catalogue and `kerf_pricing.cheap_tier`. Add a snapshot test ensuring `is_cheap_tier(provider, model_id)` agrees with the catalogue's `cheap_tier_eligible` flag for every catalogue entry.
- **Definition of Done:**
  - All 6 R-IDs above ticked in [`docs/audits/billing-holes-2026-05-24.md`](docs/audits/billing-holes-2026-05-24.md)
  - `pytest packages/kerf-render packages/kerf-billing packages/kerf-pricing packages/kerf-api packages/kerf-chat -q` green
  - A render-completion integration test exists asserting `cloud_user_balances.credits_usd` decreased by the expected amount
  - A storage-debit integration test exists asserting `monthly_storage_debit` runs on schedule

### T-402b Plug P1/P2 holes from T-401
- **Tier:** A
- **Priority:** P1
- **Status:** ✅ shipped (2026-05-24) — fan-out of 3 Sonnet worktree agents, integrated by SHA. Landed:
  - **R7** (token markup from settings, all 4 sites), **R9** (don't swallow billing exceptions — 402/503 + SSE error), **R10** (re-snapshot bucket each agent-loop iteration), **R12** (BYO decrypt failure → 402, no server-key fallback), **R14** (export rate-limit + egress usage_event), **R15** (blob-serve rate-limit; presign deferred → T-409), **R22** (operator-cost LLM calls emit `kind='operator_token'` ledger rows) → `40415932`
  - **R11** (free-quota tier resolved from `cloud_user_balances.subscription_tier` DB column, caller hint ignored), **R19** (render output uploads to object storage + presigned URL when `STORAGE_BACKEND=s3`, local fallback) → `d2a0d3a2` (proper commit in the chain, parent of `ca795e1c`; the agent worktrees chained so this landed as `ca795e1c`'s ancestor — a later attempt to cherry-pick it came up empty because it was already an ancestor. Verified single application, no duplication)
  - **R16** (explicit `paid_only` flag on every catalogue entry + test), **R17** (`/auth/forgot-password` rate-limit 5/hr), **R20** (`record_storage_event` INSERT+debit wrapped in one txn), **R21** (`BLOB_GC_DRY_RUN=false` documented as required prod env var in `deployment/koyeb.md`) → `ca795e1c`
- **Deferred:** R13 (BYO key save-validation) — no save endpoint exists yet, revisit when it lands. R15 presign-instead-of-proxy → folded into T-409.
- **Definition of Done:** pytest scoped suite at pre-existing 10-fail baseline (file_kinds + OTA + byo_blender Docker); vitest 9534/9534. ✅

### T-403 Author `koyeb.yaml` + `koyeb.worker.yaml`
- **Tier:** A
- **Priority:** P0
- **Status:** 🔴 not started
- **Scope:** Mirror `fly.toml` / `fly.worker.toml` 1:1 in Koyeb's config format. Same Dockerfile (no change), same env-var set, same Tigris S3 bindings, same pre-deploy migration command, same `/healthz` health-check. Default instance: `large` (4 vCPU, 4GB, 40GB SSD, $42.85/mo) — closest match to current `performance-2x`. Autoscale on requests (1 min, soft 200, hard 250).
- **Target files:** new `koyeb.yaml`, `koyeb.worker.yaml`, `koyeb.dev.yaml`. Leave `fly.*.toml` in place for the duration of T-405 cutover.
- **Definition of Done:**
  - Files render via `koyeb-cli validate`
  - Secrets list documented in a comment block, matches `fly.toml` exactly
  - `KERF_INPROCESS_WORKERS=true` retained by default

### T-404 `scripts/deploy-koyeb.sh`
- **Tier:** A
- **Priority:** P0
- **Status:** 🔴 not started
- **Scope:** New shell script mirroring `scripts/deploy-fly.sh`. Supports `--env dev|prod`, runs `koyeb-cli secrets sync` if needed, then `koyeb-cli deploy`. Wait for health-check pass before exit-0.
- **Target files:** new `scripts/deploy-koyeb.sh` (executable).
- **Definition of Done:**
  - `bash -n scripts/deploy-koyeb.sh` clean
  - Dry-run mode prints planned actions without executing
  - Documented in `deployment/koyeb.md`

### T-405 Smoke-test on `kerf-dev`, cut DNS, decommission Fly app
- **Tier:** A
- **Priority:** P0
- **Status:** 🔴 not started (blocked on T-403, T-404)
- **Scope:** Deploy `kerf-dev` to Koyeb. Run the e2e suite against the staging URL. Cut DNS for `kerf.sh` once green. Keep the Fly app running for 7 days as warm rollback; then `flyctl apps destroy`.
- **Definition of Done:**
  - e2e suite green against Koyeb staging
  - DNS swapped
  - Fly app destroyed; secrets purged from Fly console

### T-406 Update references — code, config, scripts
- **Tier:** A
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Sonnet fan-out (2 parallel, isolated worktrees) to replace `fly.io`, `fly.toml`, `flyctl`, `fly.storage.tigris.dev` mentions across:
  - **Agent 1 — code/scripts/config:** `scripts/*`, `Dockerfile`, `packages/**/*.py` (esp. `kerf-cloud`), env-var defaults, `SECURITY.md`.
  - **Agent 2 — docs:** `deployment/*.md`, `docs/architecture/*.md`, `decisions.md`, `CHANGELOG.md`. Add new `deployment/koyeb.md` as the canonical hosting doc. Mark `deployment/fly.md` deprecated (keep — Fly still works for CPU-only self-hosters).
- **Definition of Done:**
  - `git grep -i 'fly\\.io\\|flyctl\\|fly\\.toml'` returns only intentional historic references (CHANGELOG entries, the deprecated `deployment/fly.md`)
  - `deployment/koyeb.md` covers env vars, secrets, GPU instance selection, autoscale config, monitoring

### T-407 Update public-facing surfaces (Landing, README, ROADMAP)
- **Tier:** A
- **Priority:** P1
- **Status:** 🔴 not started
- **Scope:** Single-agent pass over public copy. The user's standing rule
  (memory: `public_readme_scope`) is that we don't list cloud-internal
  infra in public README/Landing — so the goal here is to **remove** Fly
  mentions rather than swap them for Koyeb. Where the doc legitimately
  needs to name the hosted infra (e.g. `SECURITY.md` data-flow), name
  Koyeb succinctly.
- **Target files:** `README.md`, `src/routes/Landing.jsx`, `ROADMAP.md` (rewrite the §7 entry into a single line in §4 once landed), `public/ROADMAP.md` (auto-regenerated from ROADMAP.md by predev).
- **Definition of Done:** no Fly mentions on Landing or README; the
  `SECURITY.md` data-flow names Koyeb (Frankfurt) accurately.

### T-408 Break-even monitoring dashboard
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** Cheap monthly check we run by hand initially: a SQL view +
  one-page admin route showing fixed cost (Koyeb invoice CSV, manually
  uploaded once a month) vs realised gross margin from `usage_events`.
  Goal is to make the break-even target from ROADMAP §7.1 visible.
- **Definition of Done:** admin can answer "what's our margin this month"
  in under one minute without spreadsheets.

### T-409 GPU-SKU selection policy
- **Tier:** B
- **Priority:** P2
- **Status:** 🔴 not started
- **Scope:** When dispatching a Cycles render, today the worker picks an
  arbitrary GPU. Add a small policy: small scene → rtx_a4000 / l4; medium → a6000 / l40s; large or photoreal → a100 / h100. Map from
  estimated scene complexity (poly count, lights, samples). Falls back
  to `l4` default if heuristic uncertain.
- **Target files:** `packages/kerf-render/src/kerf_render/dispatch.py` (new module or extension), corresponding tests.
- **Definition of Done:** unit tests cover three buckets (small/medium/large) and the fallback path.

### T-410 Postgres on Koyeb (optional consolidation)
- **Tier:** B
- **Priority:** P3
- **Status:** 🔴 not started
- **Scope:** Optional — only if we want one less vendor. Koyeb has a
  serverless Postgres SKU ($0.04/hr small = $29.76/mo) that maps cleanly
  to Neon. Migration is a `pg_dump | pg_restore` plus a `DATABASE_URL`
  swap. Keep Neon as a documented alternative — the engine is
  Postgres-version-portable.
- **Definition of Done:** decision recorded in `decisions.md` (keep Neon
  OR move to Koyeb). If moved: dump/restore runbook in `deployment/koyeb.md`.

