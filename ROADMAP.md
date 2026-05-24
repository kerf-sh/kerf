# Kerf — Roadmap

Strategy doc: **why / what / in what priority order.** The granular,
agent-executable backlog lives in [`tasks.md`](./tasks.md) — keep the two in
sync when priorities move. The data-model + API spec is in
[docs/architecture.md](./docs/architecture.md).

Status glyphs — exactly three, everywhere in this doc:

> `🔴 not started` · `🚧 in flight` · `✅ shipped`

---

## §1 — North Star, the LLM-native filter, the simplification principle

### North Star

**The most comprehensive CAD on Earth — a single tool in which a person can
design *anything*.** Mechanical engineering, electronics / PCB, architecture,
civil engineering, drafting, jewelry, automotive — **and every other CAD
sector, including the small and niche ones.** We are doing **everything**.
Nothing here is "cut." Lower priority means *later*, never *dropped*.

This is a **priority-ordered**, not date-ordered or effort-ordered, roadmap.
The tiers (P0→P3) express **sequence and leverage**, not a schedule and not an
estimate. Every item is committed and on the path; the order is simply which
ones earn the most credibility per unit of work.

Kerf is dual-licensed: the OSS core (MIT, see [LICENSE](./LICENSE)) and the
hosted-tier code under `packages/kerf-{billing,cloud}/` + `src/cloud/`,
governed by [LICENSE-CLOUD](./LICENSE-CLOUD).

### The LLM-native filter (the spine of everything below)

Kerf is **chat-driven** CAD. The single design constraint that orders this
whole document:

> **Every capability must be LLM-editable through a text / parametric
> representation, and the result must be verifiable.**

The litmus test applied to *any* feature, shipped or proposed:

> *Can the LLM produce and re-edit this deliverable through a text-native
> tool, and verify the result?*

Every feature sorts into exactly one of:

- **Build** — there is no text representation yet. A real capability gap.
  This is where almost all of P0–P3 lives.
- **Simplify** — the capability is genuinely needed, but professional tools
  bury it under human-UX command-discovery complexity the LLM does not need.
  Ship the *capability* (parametric core + LLM tool + text schema +
  verification), not the *UI*.
- **Skip** — the thing exists *only* as a human authoring affordance and an
  LLM makes it redundant. This is a short, tightly-bounded list (§5) and it
  **never** applies to a sector or to a correctness/output/standards feature.

### Simplification principle

Professional CAD is overcomplicated mostly because of human
command-discovery affordances (ribbons, palettes, wizards, node graphs). An
LLM needs none of that. So Kerf ships professional **capability** while
deliberately *not* shipping professional **UI complexity**. This makes the
roadmap shorter than it looks: many "pro features" are UX wrappers around a
parametric core we either have or must build once, then expose as a text
schema + LLM tool + verifier.

**Hard guardrail:** "Simplify / Skip" is about *authoring mechanics only*. It
is never an excuse to drop a domain (§2/§3 — we do everything) or to skimp on
correctness/output/standards (GD&T, Gerber/fab output, DWG handoff,
verification). Those are *more* important under an LLM, not less, because the
LLM must be able to check its own work and hand off to the real world.

---

## §1.5 — Platform foundation: own-your-data, one client, easy self-host

The sector work above only matters if a person **owns their work, isn't
locked in, and can run Kerf wherever they want.** These are not features
bolted onto the side — they are the substrate the whole product sits on, and
they order the platform spine the same way the LLM-native filter orders the
capability spine. Four commitments, all decided:

**1 — Every cloud project is a real git repository.** Not a metaphor: a
project is a git repo a user can `git clone` with stock git, no special
client and no extra tooling. Source and parametric files live in git
directly. Large or binary files are detected automatically and kept in object
storage with a small pointer committed to git, so history stays fast and the
clone stays small. Forks are near-instant and near-zero-cost because content
is shared, not copied. The version-control story is therefore two
complementary layers — fine-grained automatic file history *and* deliberate,
shareable commits with GitHub sync — not competing alternatives.

**2 — One client, cloud by default, self-host that is genuinely easy.**
`pip install kerf` gives the hosted cloud with zero setup — just
`kerf login`. Self-hosting is a fully supported, well-documented path, *not*
a hard mode: `pip install 'kerf[server]'`, point `DATABASE_URL` at a Postgres
instance you provide (a documented one-liner), then `kerf serve`. The same
client and the same data model serve both; self-host is presented as a
first-class, straightforward option. Kerf does not embed or manage its own
database — bring-your-own-Postgres is easy and documented, so embedding one
would add weight for no benefit. The only hardening here is that `kerf serve`
must fail fast with a clear, actionable message when the database URL is
missing or unreachable.

**3 — Portability is the anti-lock-in guarantee.** `kerf sync` mirrors a
project to a local folder with two-way sync, giving the local-filesystem feel
without giving up the cloud. `kerf export` / `kerf import` produce and ingest
a plain file tree. Because the cloud and the self-hosted server are
symmetric, moving a project in either direction is painless. "You own your
data and can leave any time" is a property we can demonstrate, not a promise.

**4 — A fully-local / offline / no-account desktop app is explicitly *not* a
launch pillar.** It is committed but demand-gated and post-launch. Portability
+ two-way sync + easy self-host is the complete launch answer to "I want to
own my data, not be locked in, and be able to run it myself." A standalone
offline desktop build is sequenced behind real demand, not assumed.

These four order the platform spine: git-as-substrate, the unified client,
and portability sit in the near-term priority tiers (§3) because they are
architecture-independent and gate trust for *every* persona at once; the
offline desktop app sits at the lowest tier as a post-launch, demand-gated
bet.

### §1.5.1 — Storage hygiene + comprehensive Git UX (P0, in flight 2026-05-19)

Commitment (1) above says "the version-control story is two complementary
layers — fine-grained automatic file history *and* deliberate, shareable
commits". This sub-section commits the **UX** that makes those two layers
clean and non-confusing for the user:

- **`file_revisions` becomes invisible plumbing.** It still backs Cmd+Z /
  Cmd+Shift+Z and cross-session crash recovery, but the user never sees a
  "revision history" list as a feature. Right-drawer's just-added History
  tab is removed; the activity feed stops showing keystroke `'edit'` rows.
- **Git is the only user-facing history surface.** The Git tab in the
  unified right drawer becomes comprehensive: commit graph, per-commit
  diff viewer, staged-changes view with per-file diff before commit,
  branch picker with ahead/behind, push/pull state badges, GitHub/GitLab
  sync (just wired in `2119293`).
- **Storage hygiene — users can purge revisions to free space.** Behind a
  loud confirmation ("I have committed everything I want to keep to git"),
  a purge endpoint deletes the per-keystroke revision noise while keeping
  the most recent N per file as a safety net. Git commits are unaffected
  — that's the safety net.

These tasks (**T-300 → T-306** in [tasks.md](./tasks.md)) are P0 and run
**now**, parallel across 5 Sonnet agents. They turn the platform-spine
commitment into the actual UX users will touch on every project.

**Wave 2 (2026-05-19, parallel × 3):** clean baseline migrations + collapse
the chat tool surface + wire IndexedDB crash recovery (already-built code,
unwired).

- **T-307** Fold every `alter table` / `drop` in the 12 baseline
  migrations back into the originating `create table` — single source
  of truth = the CREATE TABLE literal.
- **T-308** Tool-architecture collapse: 30+ narrow tools (`cam.run`,
  `fem.*`, `electronics.*`, …) → ~12 sharp tools (`read_file`,
  `write_file`, `edit_file`, `create_file(kind=…)`, `run_compute(engine=…)`,
  …) — per the [claude-code-guide research](./docs/architecture/runtime-state-audit.md)
  on Claude Code's actual tool design.
- **T-309** IndexedDB `localStash` crash-recovery is built but never
  wired from any editor — close the gap the runtime-state audit flagged.

---

## §2 — Per-persona deliverable scorecard

<!-- Status reconciled 2026-05-17: ECAD fab output ✅; jewelry render ✅; mechanical sheet metal/weldments/GD&T ✅ (bend table T-4 now ✅); architecture IFC Tier 2 + family editor ✅; DXF read+DWG bridge ✅; general DXF writer ✅ (T-7 shipped; DWG via ODA external); compare hub w/ per-category matrices + 14 compare pages ✅; ScrollToTop + Roadmap topbar link ✅; FEM reference-value suite + CFD foundation (potential + Navier-Stokes) ✅; body max-width:100vw h-scroll guard ✅. -->
<!-- Status reconciled 2026-05-19: aerospace applied-aero + composites CLT shipped (kerf_cad_core.aero + .composites + .matsel); silicon Phase 1+2+3 shipped (kerf-silicon — VHDL/Verilog parsers, GHDL/Yosys/ngspice bridges, GDS I/O, layout viewer, SKY130 PDK, LEF/Liberty, OpenROAD bridge, DRC, LVS, parasitics, mask fracturing); firmware shipped (kerf-firmware — board catalogue, library cache, gcc orchestrator, upload wrappers, serial monitor, LLM tool surface); viewport/frontend wire-ups: Render dropdown + Daylight mode + Exposure slider ✅ (commit 7327e7e); many sector-viewer frontend wire-ups documented in §4 Latest delta callout. -->
<!-- Planning session 2026-05-18: the platform-trust dimension (own-your-data / one client / easy self-host / portability) is now captured in §1.5 and threaded through the §3 tiers; it underpins, but does not change, the per-persona scorecard below. -->

Brutally honest. For each persona: the end deliverable they must ship, and
whether Kerf can produce it **text-natively today**.

Prioritization rationale = **AI-fit × societal importance × workforce size ×
Kerf-readiness** — this is why the P0 spine is electronics / mechanical /
drafting (high on all four today) and why civil, despite its high societal
importance, sits at P3: it is engine-gated, not low-value.

| Persona | End deliverable they must ship | Status | One-line gap |
|---|---|---|---|
| **Mechanical engineer** | Parametric solid part / assembly + a dimensioned, GD&T-toleranced drawing + STEP | 🚧 partial | Strong core (OCCT features, sketcher, assemblies+mates, tolerance stack-up, linear/modal/thermal FEM, 3/5-axis CAM, TechDraw-flavored drawings *with* GD&T frames). Sheet metal flange/unfold/flat-pattern + **bend table** (T-4) all shipped (`kerf_cad_core.sheet_metal`, `sheet_metal_bend_table`); weldments + GD&T-from-model callouts shipped. **General DXF writer shipped** (T-7; DWG via ODA external). Remaining gap: large-assembly performance (P0-5), construction-doc detailing. |
| **Electronic engineer** | A *manufacturable* PCB: schematic → routed board → **fab package** | ✅ can manufacture | KiCad-class design (ERC, hier-schematic, net classes, shove router, autoroute/freerouting DSN, length tuning, via stitching, SPICE, RF, copper pour, imports KiCad libs) + **Gerber RS-274X, Excellon drill, pick-and-place, fab BOM, IPC-2581, ODB++ zip bundle** (`kerf_electronics.fab`) + 3D board STEP export for MCAD-ECAD co-design. |
| **Architect** | Coordinated building model → IFC + construction-doc drawings | 🚧 partial | `.bim` text-DSL → IFC4 (walls/slabs/spaces/levels/site, MEP, stairs/railings, curtain wall, schedules/views/sheets) + IFC import **Tier 1 + Tier 2** (openings/MEP/families/schedules) + first-pass parametric family editor shipped. **General DXF writer shipped** (T-7; DWG via ODA external). Honest gaps vs Revit: **no native family-authoring UX** (T-109), no shipped family library (T-110), only basic wall / door / window / slab parametrics (T-111), basic stairs / ramps (T-112), early structural grid + framing (T-113), basic site / toposolid (T-114), no render-appearance BIM material catalogue (T-115); construction-doc detailing still pending. |
| **Civil engineer** | Survey/terrain → alignment/corridor → grading + plan-and-profile sheets | 🔴 cannot | Essentially **nothing** civil-specific. Needs *distinct engines* (geospatial CRS, TIN/terrain, alignment/corridor solver, hydraulics, earthwork, LandXML/IFC-4.3-infra) — not feature-adds on the B-rep kernel. In the roadmap at **P3** with each engine named honestly — highest raw societal importance (water/sanitation/roads, esp. developing world); engine-gated, hence P3 not low-value. |
| **Drafter** | Multi-sheet 2D production drawing, exchanged as DWG/DXF | 🚧 partial | TechDraw-flavored drawings shipped (multi-sheet, dimensions, GD&T frames, section hatching, leaders/balloons, centerlines). **DXF reader + DWG bridge + general DXF writer all shipped** (`kerf_imports.dxf`, `dwg/bridge.py`, `kerf_imports.dxf_writer`; R12 + R2004). DWG output via ODA external (`dwg_note()`). Remaining gap: construction-doc detailing. |
| **Jewelry CAD designer** | Rendered/printable ring or setting with stones placed and metal-weight/cost | ✅ can render | Full toolkit shipped and wired: `kerf_cad_core.jewelry.{gemstones,gem_seat,settings,ring,metal_cost}` — 7 cuts, prong/bezel/channel/pavé/channel/pavé, US/UK/EU/JP sizer + 7 shank profiles, casting-cost, FeatureView inspectors, PBR gem/metal viewport materials, casting/STL production export, preset/template library, findings, chain/bracelet. OCCT JS worker `op*` handlers fully wired (`opGemstone`/`opGemSeat`/`opJewelryProngHead`/`opJewelryBezel`/`opJewelryChannel`/`opJewelryPave`/`opRingShank`). |
| **Automotive engineer** | Class-A bodyside / component + DMU + supplier exchange | 🔴 cannot | Transfers: NURBS surfacing, FEM, 5-axis CAM, zebra/reflection-line viz (shader-side, viewport toggle). **General DXF writer shipped** (T-7; DWG via ODA external). **BIW stamping bend table shipped** (T-4). Remaining gaps: 3D harness (2D WireViz only), crash/NVH/CFD/durability (FEM is linear-static/modal/thermal only), full-vehicle DMU. See [docs/plans/automotive.md](./docs/plans/automotive.md). |
| **Education / maker / hobbyist** | A printable / CNC-able functional part, enclosure, or furniture piece + cut list | 🚧 partial | Largest reach + strongest mission (democratizing design); 3D-print slicing (`packages/kerf-slicing`, CuraEngine) + 3/5-axis CAM (`packages/kerf-cam`) shipped. Needs the simple-parametric + cut-list / flat-pack path polished and a clear on-ramp. |

---

## §3 — Priority triage

Ordered by **leverage**, not time. Automotive cross-refs preserved inline.

### P0 — credibility blockers

<!-- Status reconciled 2026-05-16: P0-1 ✅ (gerber.py/excellon.py/pnp.py/ipc2581.py/odbpp shipped); P0-3 🔴→🚧 (T-1/T-2/T-3 done, T-4 bend table not done); P0-4 ✅ (boolean hardening + faceNamingT3Booleans corpus shipped). -->
<!-- Status reconciled 2026-05-19: P0-3 🚧→✅ (T-4 bend table shipped — kerf_cad_core.sheet_metal_bend_table). -->
<!-- Planning session 2026-05-18: added the architecture-independent P0 spine — P0-6 broaden text/code file support, P0-7 project export/materialize foundation, P0-8 testing/seeding/deploy-hardening (🚧, partially landed). These are the platform-trust + quality blockers that gate the §1.5 portability guarantee and broader build-out; sized entries live in tasks.md by capability. -->

A professional in the domain hits these in the first hour; their absence
disqualifies Kerf in minute one.

| # | Persona / sector | Capability | Status |
|---|---|---|---|
| P0-1 | ECAD / PCB | **Fabrication output** — Gerber RS-274X, Excellon drill, IPC-2581 / ODB++, pick-and-place, fab BOM. Design side is KiCad-class; fab package ships in `kerf_electronics.fab` (gerber.py, excellon.py, pnp.py, fab_bom.py, ipc2581.py, odbpp/). | ✅ shipped |
| P0-2 | Architect · Mechanical · Drafter · **Automotive** | **DWG / DXF import + export.** DXF reader + entity→sketch/drawing mapper shipped (`kerf_imports.dxf`); DWG bridge shipped (`kerf_imports.dwg.bridge` + `import_dwg` tool); **general DXF writer shipped** (`kerf_imports.dxf_writer`, R12 + R2004, `export_dxf` LLM tool, T-7). DWG output via ODA external (`dwg_note()`). | ✅ shipped |
| P0-3 | Mechanical · **Automotive** | **Sheet metal** — flange / bend / unfold / flat-pattern / bend tables. Flange (T-1), unfold + flat-pattern DXF (T-2/T-3) shipped (`kerf_cad_core.sheet_metal`). Bend table per-material/thickness lookup shipped (`kerf_cad_core.sheet_metal_bend_table`, T-4). | ✅ shipped |
| P0-4 | All (chat-driven core) | **Persistent face-naming hardening** — boolean-heavy regression corpus + stress on real production models. T1–T2 landed; boolean-boundary naming (T3) + pattern/mates/sweep hardening (T4–T7) shipped (`faceNamingT3Booleans.test.js` + T4–T6 suites). | ✅ shipped |
| P0-5 | Mechanical · Architect · **Automotive** | **Large-assembly performance ceiling** — measured budget + LOD / lazy-load for 1000s of parts. Automotive full-vehicle DMU (10,000s) is the extreme case. | 🔴 not started |
| P0-6 | All (every persona) | **Broaden text / code file support** — common text and code files (`.txt` `.md` `.c` `.cpp` `.h` `.hpp` `.py` `.js` `.ts` `.json` `.yaml` `.yml` `.toml` `.ini` `.cfg` `.sh` `.ino`/`.uno` `.ld` `.v` `.vhd` and similar) open as editable text with plain highlighting **now**; proper per-language syntax highlighting follows. Architecture-independent; every project benefits. | 🔴 not started |
| P0-7 | All (platform trust) | **Project export / materialize foundation** — the plain file-tree representation that `kerf export` / `kerf import` / `kerf sync` build on (§1.5 commitment 3). The substrate for portability and the anti-lock-in guarantee. | 🔴 not started |
| P0-8 | All (engineering quality) | **Testing / seeding / deploy-hardening initiative** — broad test suites + realistic seed data + one-command local and dev loops. Partially landed; the rest of the initiative is the P0 quality gate before broader build-out. | 🚧 in flight |

### P1 — depth that converts evaluators to users

<!-- Status reconciled 2026-05-16: P1-1 ✅ (board_step.py + kicad adapter shipped); P1-2 ✅ (all jewelry worker ops wired in occtWorker.js); P1-3 ✅ (weldment.py with cut list + gdt_callouts/ shipped); P1-4 ✅ (IFC Tier 2 openings/MEP/families/schedules + parametric family editor shipped). -->
<!-- Status reconciled 2026-05-19: silicon Phase 1+2+3 ✅ (kerf-silicon T-231..T-248); firmware ✅ (kerf-firmware T-225..T-230); aerospace applied-aero + composites ✅ (kerf_cad_core.aero + .composites). -->
<!-- Planning session 2026-05-18: added the platform build-out spine — P1-8 git-as-substrate + auto large-file + free forks (🚧, large-file pointer + cloud-git layers shipped), P1-9 unified cloud-default/easy-self-host client (🚧), P1-10 sync + export/import portability. These realize the §1.5 own-your-data commitments; sized entries live in tasks.md by capability. -->

| # | Persona / sector | Capability | Status |
|---|---|---|---|
| P1-1 | ECAD / PCB | Native parts ecosystem (symbols + footprints + 3D + supplier data) and **3D board STEP export** for MCAD-ECAD co-design. KiCad adapter + BOLTS adapter + FreeCAD-library adapter shipped (`kerf_parts`); 5 fastener family generators shipped (`kerf_partsgen`); 3D board STEP export shipped (`kerf_electronics.fab.board_step`). | ✅ shipped |
| P1-2 | Jewelry | **OCCT JS worker `op*` handlers** for the shipped jewelry toolkit. All seven ops wired in `src/lib/occtWorker.js`: `opGemstone` / `opGemSeat` / `opJewelryProngHead` / `opJewelryBezel` / `opJewelryChannel` / `opJewelryPave` / `opRingShank`. Full ring renders; PBR gem/metal materials; casting/STL export; preset library. | ✅ shipped |
| P1-3 | Mechanical | Weldments (structural members + cut lists); **GD&T-from-model** on drawings. `kerf_cad_core.weldment` ships `weldment_frame` / `weldment_profile_lookup` / `weldment_cutlist`. `kerf_cad_core.gdt_callouts` ships `gdt_auto_callouts` + `gdt_callout_balloon_table`. | ✅ shipped |
| P1-4 | Architect | Parametric family editor; IFC import **Tier 2** (families / MEP / schedules / openings — Tier 1 only today); construction-doc detailing (dimensioned plans/sections, revision clouds, sheet-set mgmt). IFC Tier 2 (`openings.py`, `mep.py`, `families.py`, `schedules.py`) + parametric family editor (`kerf_bim.tools.family`) shipped. Remaining gap: construction-doc detailing. | ✅ shipped |
| P1-5 | Jewelry · **Automotive** | Surface-boolean robustness on dense NURBS — eliminate runtime escalation paths so organic models survive booleans reliably. Bounded 2-step retry ladder (`_MAX_ATTEMPTS=2`), V-column self-intersection check added, dense-NURBS near-tangent warning, `_build_tolerance_ladder` as single escalation source, `attempts` in return dict. 39-case regression corpus covering dense grids, sliver, near-tangent organic, jewelry shapes (thin bezel wall, prong-into-shank). | ✅ shipped |
| P1-6 | **Automotive** | **Class-A surfacing.** sweep/network/blend + `surface_continuity` (C0–C2 / G0–G2, no G3) + curvature-comb *visualization* + **zebra / reflection-line viewport toggle** (shader-side `ShaderMaterial`, no WASM rebuild). Algorithmic G3 structurally impossible in stock OCCT (`GeomAbs_G3` absent — verified) and stays deferred. | ✅ shipped |
| P1-7 | **Automotive** · ECAD | **3D in-vehicle wiring harness** — route through the DMU, bundle/segment/connector libs, formboard flatten, length/gauge/voltage-drop. Today only 2D WireViz `.wiring` diagrams. | 🔴 not started |
| P1-8 | All (platform substrate) | **Git-as-substrate with automatic large-file handling + free forks** (§1.5 commitment 1) — every project a stock-`git clone`-able repo; large/binary files auto-detected and kept in object storage behind a small in-git pointer; near-instant, near-zero-cost forks via shared content-addressed storage. Builds on the shipped large-file pointer + cloud-git layers toward the no-special-client guarantee. | 🚧 in flight |
| P1-9 | All (platform reach) | **Unified `pip install kerf` client — cloud-default, easy optional self-host** (§1.5 commitment 2). One client; `kerf login` for hosted; `pip install 'kerf[server]'` + bring-your-own-Postgres one-liner + `kerf serve` for self-host; fail-fast on a missing/unreachable database URL. | 🚧 in flight |
| P1-10 | All (anti-lock-in) | **Local folder sync + export / import portability** (§1.5 commitment 3) — `kerf sync` two-way folder mirror; `kerf export` / `kerf import` plain file tree; symmetric cloud ↔ self-host so data moves either way painlessly. | 🔴 not started |

### P2 — moats / breadth (tracked, not urgent)

Each is a solver-class or platform-class project; none blocks P0/P1.

- Nonlinear / explicit-dynamics (crash) / NVH / CFD / thermal-transient /
  fatigue-durability simulation (FEM is verified linear-static + modal +
  steady thermal + bonded contact only). Automotive simulation depth + EV
  packaging ride this line.
- Real-time multi-user collaboration.
- Cross-discipline clash detection.
- Scan-to-CAD / point-cloud / reverse engineering (cross-cutting, high
  leverage — touches mechanical, architecture, automotive, medical).
- Generative / lattice / DfAM (lattice partially via topology optimization).
- Robotics cell / kinematics / motion.
- Nesting / cut-optimization (laser / waterjet / plasma / sheet).
- GD&T / PMI model-based-definition + homologation documentation (shares the
  P1-3 "GD&T-from-model" gap).
- **Ladder logic + full PLC tooling** (IEC 61131-3) 🔴 — adds the
  ladder-diagram (LD) editor/representation alongside the already-shipped
  structured-text support (`.plc.st`), plus the surrounding PLC toolchain
  (lint, IEC-compliant export, rung authoring) so the automation / OT /
  electronics domain is covered end-to-end, not ST-only.
- **Embedded / firmware programming + integrated build toolchain** ✅ —
  Arduino (`.ino` / `.uno`), C / C++ / `.h`, broader programming-language
  support, and an integrated **compile + flash** pipeline: GCC-class
  cross-compilers (`avr-gcc`, `arm-none-eabi-gcc`, ESP/xtensa), board +
  toolchain management, build/upload/serial-monitor. kerf-firmware package
  shipped: board catalogue, library cache, direct-gcc orchestrator, upload
  wrappers, serial monitor, LLM tool surface (T-225..T-230). P0-6 broadened
  text/code file support gates the per-language editor depth (still 🔴).

### P3 — long-tail verticals & distinct-engine domains

**Everything else, all committed, lowest priority.** This is the proof that
"we do everything." Each line is a real domain on the path; many reuse the
parametric/partsgen spine, a few need distinct engines (named explicitly).

**Mechanical / product:** plastics & injection-mold tooling ✅ (kerf_cad_core.injection — mold-flow fill time, cavity pressure, shrinkage, injection-unit checks) · casting /
forging / die design ✅ (kerf_cad_core.casting — solidification, shrinkage, riser sizing, Chvorinov; kerf_cad_core.forming — forming limit, springback, blank sizing) · packaging / dieline (folding carton, corrugated)
✅ (kerf_cad_core.packaging — dieline gen, crease pattern, glue-flap, stackability) · springs ✅ (kerf_cad_core.springs — helical compression/extension/torsion, Belleville washer; Wahl/Goodman/Almen-László) · gears ✅ (kerf_cad_core.gears — involute spur/helical, AGMA strength; kerf_cad_core.gearstrength; gearbox; wormbevel) · cams generators 🔴 (kerf-partsgen-reachable) · piping
/ P&ID / plant design ✅ (kerf_cad_core.piping — Darcy-Weisbach, pipe stress, supports, P&ID symbols) · HVAC duct fabrication ✅ (kerf_cad_core.hvac — duct sizing, heat load, psychrometrics) · hydraulic / pneumatic
manifold ✅ (kerf_cad_core.fluidpower + kerf_cad_core.pneumatics).

**Electronics:** IC / VLSI / silicon layout ✅ (kerf-silicon — VHDL/Verilog parsers, GHDL/Yosys/ngspice bridges, GDS I/O, layout viewer, SKY130 PDK, LEF/Liberty readers, OpenROAD bridge, DRC, LVS, parasitics, mask fracturing — T-231..T-248) · power one-line / switchgear 🔴 ·
lighting / photometric 🔴 (cable/harness 3D tracked at P1-7).

**Architecture:** structural RC / steel + rebar ✅ (kerf_cad_core.concrete — ACI 318 RC design; kerf_cad_core.struct — AISC steel frame/grid; kerf_cad_core.timber — NDS timber design; kerf_cad_core.steelconn — bolted/welded connections) · interior /
space-planning / FF&E 🔴 · kitchen / bath / cabinetry / millwork 🔴 ·
landscape 🔴 · fire-protection / sprinkler ✅ (kerf_cad_core.firesafety — sprinkler spacing, pipe sizing, suppression loads) · scaffolding / formwork 🔴 ·
energy / daylight / acoustic ✅ (kerf_cad_core.buildingenergy — EnergyPlus-style load calc, U-values, HVAC sizing; kerf_cad_core.acoustics — room acoustics, STC, NRC).

**Civil / infrastructure (distinct engines, named):** geospatial CRS engine
✅ (kerf_cad_core.geodesy — ellipsoid, Helmert, UTM/MGRS, CRS transforms) · TIN terrain + contours + cut/fill 🚧 (earthworks module ships cut/fill volume; TIN triangulation pending) · horizontal/vertical alignment +
corridor solver ✅ (kerf_cad_core.civil — spiral easements, superelevation, sight distance, VC design; cross-section corridor) · hydraulics / stormwater ✅ (kerf_cad_core.hydrology — rational method, SCS/CN, IDF, detention-basin routing; kerf_cad_core.civil.hydraulics — Darcy, Manning, Hardy-Cross) · grading / earthwork ✅ (kerf_cad_core.earthworks — prismatoid volumes, borrow-pit, mass-haul, Moody chart) ·
plan-and-profile sheet engine 🔴 · LandXML + IFC-4.3-infra I/O 🔴 ·
bridge/tunnel 🔴 · water/wastewater 🔴 · geotechnical ✅ (kerf_cad_core.geotech — bearing capacity, settlement, slope stability, SPT/CPT correlation) · mining 🔴 ·
marine/dredging 🔴 · rail signaling 🔴.

**Vehicles:** aerospace ✅ (applied aerodynamics — ISA atmosphere, VLM/thin-airfoil, flight mechanics, propulsion, Breguet range/endurance; 6-DOF, orbital mechanics, ADCS, thermal network, LLM tool surface — `kerf_cad_core.aero`; composites CLT shipped — `kerf_cad_core.composites`) · composites ply/layup authoring 🔴 (draping / fiber-steering / Fibersim class) · marine / naval-architecture ✅ hydrostatics (kerf_cad_core.navalarch — displacement, form coefficients, GZ stability, trim, resistance)
· hull fairing 🔴 (NURBS-reachable; T-71 seed pending) ·
rail rolling stock ✅ (kerf_cad_core.railway — track geometry, cant/superelevation, curve resistance, signal spacing). (Automotive itself tracked at P1-6/P1-7/P2.)

**Body-worn / medical / craft:** watchmaking / horology 🔴
(partsgen-reachable) · eyewear / frames 🔴 · footwear / last design 🔴 ·
dental CAD (crowns / aligners) 🔴 · orthopedic / prosthetics / implants 🔴 ·
hearing aids 🔴. (Jewelry tracked at P1-2.)

**Soft goods (distinct 2D/developable engine):** apparel / pattern-making +
drape 🔴 · technical textiles / sails / membrane / tensile 🔴 · upholstery /
leather 🔴.

**Fabrication:** laser / waterjet / plasma + nesting ✅ (kerf_cad_core.nesting — 2D pack, kerf/margin, rotation; LLM tools) · woodworking /
furniture / joinery + cutlist 🔴 · robotics cell / kinematics ✅ (kerf_cad_core.robotics — serial arm FK/IK/Jacobian/trajectory; kerf_cad_core.kinematics — four-bar linkage). (Sheet
metal is P0-3 ✅; lattice/DfAM is P2; 3-print slicing + 3/5-axis CAM shipped.)

**Scientific / niche:** optical / lens / ray-trace ✅ (kerf_cad_core.optics — lensmaker, thin-lens / mirror / two-lens imaging, Gaussian beam, MTF) · microfluidics / MEMS
🔴 · wind-turbine / large-energy structures ✅ (kerf_cad_core.windturbine — BEMT rotor, power coefficient, tip-speed ratio, Weibull capacity factor) · theatrical / stage / rigging
✅ (kerf_cad_core.rigging — sling load, wire-rope capacity, shackle/pulley) · signage / large-format 🔴.

**Platform (post-launch, demand-gated):** fully-local / offline / no-account
**desktop app** 🔴 — committed but explicitly **not a launch pillar** (§1.5
commitment 4). The launch answer for "own my data / not locked in / run it
myself" is portability + two-way sync + easy self-host (P0-7, P1-9, P1-10);
the standalone offline desktop build is sequenced behind real demand.

**How to extend P3:** an uncovered sector is never "out of scope" — it is a
new line here plus one or more sized tasks in [`tasks.md`](./tasks.md). The
default home for a new sector is P3 unless it is a credibility blocker for an
existing persona (then P0/P1).

---

## §3.5 — Advanced cross-cutting capabilities (strategic AI-leverage)

These are not P3 filler. They are the **AI-native moat**: capabilities that
have no real equivalent in legacy CAD and that an LLM makes *more* powerful,
not less, because their substrate is **math, rules, or text** — exactly what a
chat-driven engine manipulates best. Each spans *every* sector simultaneously
(a simulation engine serves mechanical, automotive, civil, and aerospace at
once), so they compound leverage instead of adding it linearly. They are
**roadmap-level / strategic** and intentionally **not** yet decomposed into
[`tasks.md`](./tasks.md) tasks — they earn tasks only when a specific slice is
promoted to near-term P0/P1.

| Capability | Reference tools | Why it's AI-native / why it matters | Status |
|---|---|---|---|
| **Implicit / function-rep (F-rep / SDF) modeling** | nTopology, ImplicitCAD | Field-driven lattices / TPMS / gradient materials. Geometry expressed as a math function is the *ideal* LLM substrate — no topology bookkeeping, infinitely composable, verifiable by sampling the field. **Shipped:** `kerf_cad_core.frep.sdf` — SDF primitives, CSG ops, transforms, TPMS lattices, marching-cubes mesh extraction, volume/surface-area integration, LLM tools. | ✅ shipped |
| **Generative / topology / multi-objective optimization (production-grade)** | Fusion Generative, nTop, OptiStruct | Manufacturing-constrained, multi-load-case, multi-objective, lattice-infill optimization. The LLM frames the objective + constraints in text and reads back a verified result. Verified: basic single-objective SIMP topo-opt shipped (`packages/kerf-topo`, FEniCSx); manufacturing constraints / multi-load / multi-objective / lattice-infill **not** — the deep, production-grade version is unbuilt. | 🚧 in flight |
| **Simulation pillar** *(user priority — emphasized)* | Abaqus, LS-DYNA, nCode, OpenFOAM / Ansys, Adams | Nonlinear FEA, explicit dynamics / crash, fatigue & durability, CFD, low/high-frequency EM, acoustics, multibody dynamics, coupled multiphysics. Physics is governing equations + boundary conditions = text; the LLM sets up the study and self-checks results. **Verified split:** `packages/kerf-fem` analysis enum was `linear_static \| modal \| thermal` (+ bonded contact) — that slice ✅ shipped, and a **reference-value suite** with citable Roark / Blevins / Incropera oracles (`pressure_load.py` + 43-test `test_fem_refvalues.py`, 42 green, one ASTM E1049 rainflow test skipped — `fatigue_fem._rainflow` bug flagged) landed this session. A **parallel FEM-hardening stream** is still in flight to match CalculiX / Z88 / Mystran depth (T-100); seed modules for `nonlinear`, `explicit`, `acoustics_fem`, `em_field`, `em_highfreq`, and `fatigue_fem` are present in `packages/kerf-fem/src/kerf_fem/` but not yet wired through the public analysis enum. **CFD foundation** also landed this session — `cfd_potential.py` (potential flow, `Cp(θ)=1−4sin²θ` analytic oracle) + `cfd_navier_stokes.py` (lid-driven cavity, Ghia Re=100 reference), 61 hermetic tests in `test_cfd.py`, **2-D laminar scope**; full CfdOF-class depth (turbulence k-ε / k-ω SST, 3-D unstructured meshing, OpenFOAM bridge) tracked at T-101. **Crash / multibody / coupled multiphysics still 🔴 not started.** | 🚧 in flight |
| **1D system simulation** | Modelica, Amesim, Simulink | Lumped-parameter thermal / hydraulic / electrical / control networks. Modelica is *text* — a declarative equation-based language — making this exceptionally AI-native. **Shipped:** 16 DAE components (mechanical / hydraulic / pneumatic / thermal / control); MSD + pump-tank + ε-NTU validated. | ✅ shipped |
| **Manufacturing process simulation** | Moldflow, MAGMASOFT, AutoForm, Vericut | Mold-flow, casting solidification, stamping / forming, AM residual stress, machining (toolpath) verification, weld distortion. **Shipped:** moldflow Hele-Shaw front tracking + weld-line + air-trap (`moldflow/flow_front.py`); casting solidification + Chvorinov + riser sizing + gating (`kerf_cad_core.casting`); stamping / forming limit + springback + blank sizing (`kerf_cad_core.forming`). Remaining: AM residual stress, Vericut-class toolpath verification, weld distortion. | 🚧 in flight |
| **Automatic Feature Recognition (AFR)** | (re-parameterize imported "dumb" STEP into editable features) | Critical AI enabler: turns any imported boundary-rep solid into an editable parametric feature tree, so the LLM can edit *any* model — not just ones authored in Kerf. Verified absent (no feature-recognition module). | 🔴 not started |
| **Knowledge-based engineering / design automation / code-compliance** | KBE, DriveWorks | Engineering rules + standards checks (Eurocode / AISC / ACI / ASME / ISO) driven directly by the model. Rules and standards are *text* — extremely AI-native and a large differentiator. **Shipped:** AISC 360-22 + ACI 318-19 + Eurocode EC2/3/5/8 + NDS 2018 + ASCE 7-22 + ISO 6336 + IAPWS-IF97 + IEEE 1584 + IEC 60255 — per-code compliance checks across structural, electrical, and manufacturing domains. General KBE configurator layer 🔴 not started. | 🚧 in flight |
| **3D tolerance / variation analysis** | 3DCS, CETOL | Statistical stack-up + contributor analysis in 3D. **Shipped:** 1D worst-case / RSS / Monte-Carlo (`packages/kerf-mates` `tolerance.py`) + 3D vector-loop stackup with 6-DOF Jacobian sensitivity (`tolstack/tol3d.py`). Full statistical 3DCS-class variation simulation (FEA-coupled) still ahead. | 🚧 in flight |
| **PLM depth** | (product configurator, 150% / effectivity BOM, where-used, ECR / ECO, digital thread, MBSE / SysML traceability) | The digital thread is structured data + relationships = ideal for an LLM to traverse and keep coherent. Verified: file revisions + cloud git + configurations / variants + BOM rollup shipped (partial PLM); deep PLM (configurator, 150% / effectivity BOM, where-used, ECR/ECO, MBSE/SysML trace) **🔴 not started.** | 🚧 in flight |
| **Multi-CAD interop & geometry healing** | STEP AP242 / JT / Parasolid / QIF + automatic repair | Robust import/heal is what lets the LLM operate on the real-world ecosystem, not a walled garden. Verified: STEP I/O shipped; **AP242 / JT / Parasolid / QIF + automatic geometry healing 🔴 not started** (only internal ShapeFix passes inside surface booleans, not a general heal tool). | 🚧 in flight |
| **Reverse-engineering pipeline** | Geomagic, PolyWorks | Point cloud → segmentation → feature fit → parametric solid. Verified absent as a pipeline; quad-remesh (`packages/kerf-cad-core` `quad_remesh.py`) is an adjacent, reusable building block. | 🔴 not started |
| **Mechanism synthesis & motion** | MotionGen, Adams | Linkage / cam / gear-train *synthesis* + kinematics. Synthesis is an inverse problem stated in text (motion spec → mechanism) — very AI-native. Verified: mates constraint solver shipped (`packages/kerf-mates` `solver.py`); **mechanism synthesis 🔴 not started.** | 🚧 in flight |
| **Sustainability / LCA** | One Click LCA | Embodied-carbon / circularity computed straight from the model + a materials database. Data-native, increasingly *mandated* by regulation. **Shipped:** full ISO 14040/44 LCA — 4 phases (cradle/use/transport/EoL), impact categories GWP/AP/EP/HTP/water/PM2.5 + Monte-Carlo uncertainty (`kerf-lca/phases.py`); Ashby materials database expanded to ~200 materials with Pareto-frontier multi-objective selection. | ✅ shipped |
| **Robotics / offline programming** | RoboDK, Process Simulate | Robot-cell simulation + path generation. Toolpaths and robot programs are text — naturally AI-native. **Shipped:** `kerf_cad_core.robotics` — DH-matrix, FK chain, end-effector pose, IK (2R/3R planar), geometric Jacobian, manipulability, workspace radius, trapezoidal joint trajectory; `kerf_cad_core.kinematics` — planar four-bar linkage (Grashof check, position, transmission angle, coupler curve). LLM tools registered. | ✅ shipped |
| **Nesting / cut & material optimization** | (sheet / textile / wood / stone nesting) | Cross-cutting, high-leverage packing/optimization shared by laser/waterjet/plasma, woodworking, apparel, and stone — one solver serves many sectors. **Shipped:** `kerf_cad_core.nesting` — 2D part nesting (bin-packing with rotation, kerf/margin awareness, LLM tools `nest_parts_tool` + `nest_report_tool`). | ✅ shipped |

### §3.5a — Firmware / embedded as a direct-gcc orchestrator (the layer that *drives* the PCB)

The existing `kerf-firmware` (T-130) is a thin PlatformIO Core CLI subprocess
wrapper. It works, but it has two structural problems we want to leave behind:
(1) it puts the entire build behind a third-party CLI we do not control, and
(2) `platformio.ini` is a different file format from the rest of Kerf, which
is JSON-everywhere. The replacement direction — **decided 2026-05-18** — is to
write our own thin **direct-gcc orchestrator** that subprocesses the
cross-compilers themselves (`avr-gcc`, `arm-none-eabi-gcc`, `xtensa-esp32-gcc`,
`riscv-none-elf-gcc`), the same pattern as our CalculiX / Z88 / Mystran
bridges. PlatformIO's **library registry** (a public REST API at
`api.registry.platformio.org/v3`) and Arduino's `library_index.json` stay —
they are the ecosystem — but we stop subprocessing `pio`.

The strategic frame: **Kerf already does the PCB.** Adding firmware closes the
loop end-to-end — a single project authored in chat designs the schematic,
routes the board, generates the Gerbers, **and writes the firmware that runs
on the MCU it just designed.** When mechanism actuators land (P2), the same
project also simulates the actuator that the firmware drives. **One project,
multiple layers** — that is the moat no incumbent tool offers because no
incumbent tool sits across mechanical / electronic / firmware / simulation at
once. Tickets T-225..T-230 in [`tasks.md`](./tasks.md) scoped the rebuild and
have **all ✅ shipped** — the direct-gcc orchestrator now subprocesses
`avr-gcc` / `arm-none-eabi-gcc` / `xtensa-esp32-gcc` / `riscv-none-elf-gcc`
directly; PlatformIO's library registry + Arduino's `library_index.json` are
called over HTTP; `kerf.fw.json` is the JSON-everywhere project manifest;
upload wrappers (avrdude / esptool / stm32flash / bossac) + serial monitor
(pyserial + WebSerial) + `make_arduino_sketch(spec)` LLM tool all landed.
Depth follow-ups (RTOS primitives, OTA, RTOS-aware debug, power profiles,
pin-map cross-check vs PCB, USB-class drivers) are queued as T-259..T-265.

**Why direct-gcc, not `subprocess pio`:**

- The library registry is a *public REST API*, not a CLI: we can call
  `https://api.registry.platformio.org/v3/libraries` and Arduino's
  `library_index.json` directly. Library packaging is well-documented
  (`library.json` / `library.properties`), so we parse manifests ourselves.
- Toolchains are stock cross-`gcc` binaries we can fetch (or bake into a
  Docker layer in the cloud) — the same operational pattern we already run
  for CalculiX / Z88 / Mystran / Blender Cycles. No `pio` runtime needed.
- We own a JSON project manifest (`kerf.fw.json`) interconvertible with
  `platformio.ini`, but **JSON-everywhere matches the rest of Kerf** —
  `equations`, `configurations`, `feature`, `wiring`, `plc` are all
  JSON-native. The LLM edits one schema family, not two.
- Cleaner separation of "what is the build" (our orchestrator) from
  "what is the toolchain" (vendor gcc). When ESP-IDF or Zephyr matters,
  we add an orchestrator profile; we never ship someone else's CLI.

| Capability | Reference | Status |
|---|---|---|
| **Board catalogue** mirroring ~200 popular boards (Arduino UNO/Nano/Mega, Teensy 3.x/4.x, STM32 BluePill/Nucleo, ESP8266/ESP32 family, RP2040, AVR/ATtiny, SAMD21/SAMD51, nRF52, ESP32-C3/S3 RISC-V) with MCU / arch / flash / RAM / pin-map metadata | PlatformIO `boards.json` | ✅ shipped (T-225) |
| **Library registry HTTP client** — PlatformIO v3 + Arduino library_index.json + content-addressed cache that dedups libraries across user projects (same pattern as Git LFS) | api.registry.platformio.org/v3 | ✅ shipped (T-225, T-226) |
| **Direct-gcc build orchestrator** — per-architecture build profiles, subprocess `avr-gcc` / `arm-none-eabi-gcc` / `xtensa-esp32-gcc` / `riscv-none-elf-gcc` | CalculiX/Z88-pattern subprocess bridge | ✅ shipped (T-227) |
| **Upload wrappers** — `avrdude`, `esptool.py`, `stm32flash`, `bossac`. Local CLI only (needs physical USB) — cloud surfaces a "this requires the local Kerf CLI" hint | avrdude/esptool/stm32flash | ✅ shipped (T-228) |
| **Serial monitor** — pyserial in the local CLI, WebSerial in the browser when supported | pyserial / WebSerial API | ✅ shipped (T-229) |
| **LLM tool `make_arduino_sketch(spec)`** + `kerf.fw.json` schema | new | ✅ shipped (T-230) |
| **Firmware depth follow-ups** — RTOS primitives, embedded LLM tool catalogue (I2C/SPI/UART/CAN/OneWire), OTA, RTOS-aware debugger, power profiling, pin-map cross-check vs PCB, USB-class drivers | FreeRTOS / Zephyr / Arduino libs | 🔴 not started (T-259..T-265) |

### §3.5b — Silicon / EDA / VHDL — open-source full-flow chip design

**Strategic bet:** ~80 % of the silicon-design flow is now open source, but no
one has assembled it into a **cloud-native, AI-native, browser-accessible**
tool. We do. This is the same move we made on electronics (we are KiCad-class
in a browser, chat-driven) one layer deeper into the stack — the **physical
fabrication** layer of the device. We compete directly with Cadence Virtuoso,
Mentor Calibre, and Synopsys Design Compiler — tools that cost ~$1 M / seat /
year and are gatekept behind university and corporate licences. The
open-source primitives that make this reachable in 2026:

- **VHDL** (IEEE 1076) → **GHDL** v6.0 — the only mature open VHDL simulator,
  GCC/LLVM-backed, fast.
- **Verilog / SystemVerilog** (IEEE 1364 / 1800) → **Verilator** v5 (compiled,
  ~100× faster than interpreted) for production sims + **Icarus Verilog** for
  the long tail of behavioural constructs Verilator does not cover.
- **Modern Python-embedded HDL** → **Amaranth HDL** (formerly nMigen) for
  designs authored *in the LLM substrate*: Python that elaborates to Verilog.
  Amaranth is exceptional AI-fit — Python is what the LLM writes natively.
  We also recognise Chisel (Scala) and SpinalHDL (Scala) — supported via
  import, not as our primary authoring path.
- **Synthesis** → **Yosys** (ISC) — RTL → gate-level netlist. Production-grade,
  used in every open-flow tape-out to date.
- **Place & route + full RTL→GDS-II** → **OpenROAD** + **OpenLane / OpenROAD
  Flow**. Tape-out-proven in **600+ silicon-ready tape-outs** on Skywater 130 nm
  and GlobalFoundries 180 nm via the Efabless MPW programme.
- **PDK** (process design kit) → **Skywater SKY130** (the world's first true
  open PDK), **GF180MCU**, **IHP SG13G2 130 nm BiCMOS** (newer, analog-
  friendly). All Apache-licensed.
- **Mixed-signal SPICE** → **ngspice** (already used inside `kerf-electronics`)
  + **Xyce** for larger circuits. Extends straight from board-level into
  device-level.
- **Layout viewer / editor** → **KLayout** — Python-scriptable GDS-II + OASIS
  + CIF + DXF reader/editor; we adopt its data model for our in-browser
  viewer (SVG / Canvas; no `klayout` GUI in the browser, but a thin reader
  that emits the same Python AST KLayout exposes).
- **Formats**: `.gds` / `.oas` (mask layout), `.lef` / `.def` (standard-cell
  abstract + design exchange), `.lib` (Liberty timing characterisation),
  `.v` / `.sv` / `.vhd` / `.vhdl` (HDL source), `.spice` / `.cir` (netlists).
  All append cleanly to `files_kind_check` in a single deferred migration.

**Phasing.** Three phases, each independently usable. Phase 1 is a real
front-end (RTL editing + behavioural simulation + sub-process bridges to
production tools), Phase 2 is a real back-end (layout, PDK, RTL → GDS-II),
Phase 3 is the verification + characterisation depth that distinguishes
"educational" from "tape-out-ready." Tickets T-231..T-248 cover all three —
**Phase 1 + Phase 2 + Phase 3 are now essentially complete (✅ shipped 2026-05-19).**
**Phase 4 — verification depth + post-silicon** (cocotb-style Python testbench
harness, power analysis from extracted parasitics + Liberty, static timing
analysis, clock-tree synthesis, antenna + latch-up DRC extensions, formal
equivalence checking, Tiny Tapeout + Efabless / Caravel harness packagers,
open analog-cell library) is queued at T-249..T-258.

| Phase | Tickets | Capability | Status |
|---|---|---|---|
| **Phase 1 — RTL front-end** | T-231..T-236 | Pure-Python VHDL + Verilog lexer/parser, behavioural VHDL event-driven scheduler with delta cycles, Yosys subprocess bridge, GHDL subprocess bridge, ngspice mixed-signal extension. Educational + small-design tape-out path. | ✅ shipped |
| **Phase 2 — Layout back-end** | T-237..T-242 | GDS-II reader/writer (pure Python; KLayout-shape data model), in-browser layout viewer (SVG/Canvas — no klayout GUI), Skywater 130 nm PDK integration, LEF/DEF reader, Liberty (`.lib`) reader, OpenROAD/OpenLane subprocess flow producing real GDS-II from RTL. | ✅ shipped |
| **Phase 3 — Verification + characterisation** | T-243..T-248 | Schematic→mask flow, DRC engine, LVS (layout-vs-schematic), parasitic extraction, photolithography mask generation, characterisation for a target PDK node. | ✅ shipped |
| **Phase 4 — verification depth + post-silicon** | T-249..T-258 | Cocotb-compatible Python testbench harness, power analysis from parasitics + Liberty, static timing analysis, clock-tree synthesis seed, antenna check + latch-up DRC extensions, formal equivalence checking, Tiny Tapeout + Efabless / Caravel harness packagers, open analog-cell library (op-amps / comparators / bandgaps). | 🔴 not started |

The competitive frame is *not* "we replace Virtuoso in 18 months" — it is
"we are the only browser-accessible chat-driven RTL-to-GDS-II tool" the
moment Phase 1 + Phase 2 land. That alone is a defensible moat for the
education / hobbyist / startup-tape-out segment (Tiny Tapeout, Efabless
MPWs, university courses) that is impossible to address with desktop
licensed tools. Phase 3 promotes us to credibility-with-Industry. P3 already
lists "IC / VLSI layout" as a long-tail sector; that line is now elevated by
this concrete plan and the tickets in [`tasks.md`](./tasks.md).

---

### §3.5c — Aerospace depth — flight + structures + space

We have aerospace-adjacent pieces shipped: Mystran NASTRAN bridge (T-100g) handles
structural / modal / aeroelastic FEM, OpenFOAM bridge (T-101d) + k-ω SST (T-101b)
handle viscous CFD, composites (T-173) ships drape/CLT/failure-seed, STEP AP203/214
(T-156/T-157) is the canonical aerospace interchange. The honest gap: **everything between
the structure and the trajectory** — the layer where engineers actually design wings,
plan launches, size engines, control spacecraft attitude.

Top 10 gaps (P1, **all ✅ shipped 2026-05-19** — `packages/kerf-aero/` carries the
full stack):

| # | Gap | Why it matters | Status |
|---|-----|----------------|--------|
| 1 | **Vortex-lattice / panel-method aero (VLM, XFOIL-class)** | Wing design, polars, lift-distributions; the bread-and-butter low-speed aero solver | ✅ shipped (`vlm.py` + `panel_2d.py`) |
| 2 | **Aeroelasticity / flutter (NASTRAN p-k method, doublet-lattice)** | Aircraft cert blocker — must clear flutter speed before flight | ✅ shipped (`flutter_pk.py` + `doublet_lattice.py` + `aeroelasticity.py`) |
| 3 | **Airfoil library** (NACA 4/5-digit gen + UIUC Selig DB, ~1500 airfoils) | First click of any aero design | ✅ shipped (`airfoils/{naca,selig,database}.py`) |
| 4 | **6-DOF flight dynamics** + ISA atmosphere | Aircraft/rocket trajectory, autopilot, control derivatives | ✅ shipped (`flight_dynamics/{sixdof,atmosphere,coefficients}.py`) |
| 5 | **Orbital mechanics** (Kepler/Lambert/Hohmann + J2/J3 perturbations) | Sat/spacecraft missions, launch trajectory | ✅ shipped (`orbital/{kepler,lambert,transfers,perturbations}.py`) |
| 6 | **Rocket propulsion / NASA CEA** (chemical-equilibrium engine perf) | Liquid + solid + hybrid engine design | ✅ shipped (`propulsion/{cea_lite,nozzle,rocket_eq,staging}.py`) |
| 7 | **Composite laminate failure depth** (Tsai-Wu, Tsai-Hill, interlaminar shear) | Composite cert path — extends T-173 | ✅ shipped (depth folded into `kerf-composites`) |
| 8 | **Aerospace materials DB** (7075-T6, Ti-6Al-4V, Inconel 718, CFRP prepreg) | Stress + thermal + fatigue inputs | ✅ shipped (folded into `kerf-cad-core/materials/`) |
| 9 | **Spacecraft ADCS** (quaternion attitude + reaction wheels + magnetorquers) | Smallsat / cubesat customer base | ✅ shipped (`adcs/{attitude,reaction_wheels,magnetorquer,control_allocation}.py`) |
| 10 | **Spacecraft thermal control** (radiative network, view factors, solar flux) | Smallsat / cubesat thermal design | ✅ shipped (`thermal/{network,view_factors,solar_flux,coatings}.py`) |

Tracked-but-not-yet-prioritised aerospace gaps (kept honest) — **promoted to P1
follow-up tickets T-266..T-272 (queued 2026-05-19)**:
- **XFOIL-class viscous solver** (boundary-layer + transition) — extension to the shipped VLM panel — T-266
- **Aircraft conceptual sizing** (Raymer / Roskam weight-fraction method) — T-267
- **Stability derivatives** (Cl_α, Cn_β, Cm_α, control-effectiveness tables) — T-268
- **Aero-acoustics** (FW-H equation, engine + propeller noise) — T-269
- **Heat-shield / ablation** for re-entry — T-270
- **Aerospace fasteners** (Hi-Lok, Cherry, NAS/MS/AS standards) — T-271
- **DO-178C / DO-254** certification doc artefacts (software / hardware) — T-272

Once these land, the residual unbuilt slice is CFD-visualisation polish
(streamlines / shock detection / vortex-core extraction) which rides the
CFD foundation (T-101) rather than aerospace-specific code.

The cluster mostly lives in a new `packages/kerf-aero/` package, with depth extensions
flowing back into `kerf-composites` (T-173) and `kerf-cad-core/materials/` (T-115/T-214).
ngspice already covers analog/RF (electronics). The convergence framing: tscircuit/atopile
designs the avionics PCB → kerf-firmware (T-225..T-230) flashes the autopilot →
kerf-aero/flight_dynamics simulates the trajectory the autopilot will fly. **One project,
many layers** — the same moat shape as electronics/firmware/motion.

---

### §3.5d — Frontend integration debt (wire-up backlog T-273..T-280)

The §3.5a / §3.5b / §3.5c backends shipped fast — fast enough that the
frontend has not yet caught up. The work in this sub-section is **not new
capability**; it is the wire-up that converts those Python packages from
"we have it" into "an evaluator can click it." It is sequenced ahead of new
sector work because a shipped capability that no user can reach pays no
credibility dividend.

| # | Frontend gap | Backend already shipped | Ticket |
|---|--------------|-------------------------|--------|
| 1 | LayoutViewer accepts a real GDS upload + renders with SKY130-coloured palette | T-237 (GDS-II I/O) + T-238 (viewer) + T-239 (SKY130) | T-273 |
| 2 | Firmware Build / Upload / Monitor buttons wired into the file-tree right-rail | T-225..T-230 (full firmware pipeline) | T-274 |
| 3 | Comparison matrix gains silicon (vs Cadence / Synopsys), firmware (vs PlatformIO / Arduino IDE), aerospace (vs ANSYS Fluent / STK) columns | T-225..T-248 + aerospace top-10 | T-275 |
| 4 | `/silicon`, `/firmware`, `/aerospace` domain landing routes | all three packages | T-276 |
| 5 | Docs-viewer LLM consolidation indexes `kerf-silicon` / `kerf-firmware` / `kerf-aero` llm_docs | all three packages have `llm_docs/` | T-277 |
| 6 | New-file dialog surfaces `.vhd` / `.v` / `.sv` / `.gds` / `.lef` / `.lib` / `.spice` / `.fw.json` / `.ato` / `.ino` as first-class types | T-248 (file-kind enum) | T-278 |
| 7 | Landing page sector cards for silicon + firmware + aerospace | new sector landings (T-276) | T-279 |
| 8 | Cmd-K command-palette indexes file-kinds + package docs so silicon / firmware tooling is discoverable | T-248 + T-277 | T-280 |

This is shipped-but-invisible debt; it pays back as soon as it lands. Once
T-273..T-280 close, the next round of sector work (§3.5 implicit / F-rep,
§3.5 1D system simulation, the §3 P3 long-tail) starts from a clean wired-up
frontend, not a backend-only shipment.

---

### §3.5e — Textiles / fashion / soft-goods (T-281..T-286)

T-179 shipped the 2D pattern-making seed (blocks + seam allowance + grading
+ marker). The full textile-design layer rides on top of that with weave/
knit pattern generators, drape simulation (leveraging the kerf-motion RK4
integrator from T-163), dye-sublimation + screen-print art alignment,
production-scale cut-room nesting, e-textile / smart-textile integration
(conductive thread routing + PCB-fabric transition), and a curated 50+
textile materials catalogue with sustainability metrics (LCA / GOTS /
OEKO-TEX / Bluesign).

Why this is a kerf-shape unlock and not a generic CAD feature: the
**LLM-native chat surface** can take a brief like "design a pleated
midi-skirt for a model with these measurements, in organic cotton,
heat-bondable with conductive thread for LED hem" and walk through all six
layers (pattern → drape → print art → cut room → e-textile routing →
sustainability score) in one conversation, producing the cut files, the
sub PCB design (via the existing electronics stack), and a sustainability
report at the end. Most CAD competitors require 4-5 separate tools.

P2 — sequenced after the §3.5d wire-up debt closes.

---

## §4 — Shipped ledger (condensed)

One line per shipped capability. Detail lives in the linked plan/doc — the
roadmap no longer narrates it.

### Latest delta (2026-05-24)

What landed in the session ending 2026-05-24. All items ✅ as of this sync.

**Structural code design** ✅ — AISC 360-22 members (Ch. E compression + F LTB W/C/HSS/pipe/angle + H combined) + bolted/welded connections + base-plate (LRFD+ASD); ACI 318-19 flexure/shear/PM/development-length + punching-shear §22.6 + torsion §22.7; NDS 2018 timber (full adjustment factors); ASCE 7-22 LRFD+ASD load combos + ELF + RSA (SRSS+CQC) + Newmark time-history seismic (SDOF 0.07 % error). Full Eurocode coverage: EC2 (concrete flexure/shear/punching/deflection) + EC3 (steel members/connections) + EC5 (timber, NDS-parity) + EC8 (spectrum/LFM/RSA).

**Native FE** ✅ — MITC4 (Bathe-Dvorkin) plate/shell element with consistent mass matrix + modal analysis via inverse iteration (1.29 % error vs Timoshenko at 16×16); 2D/3D frame stiffness assembler with ASCE 7 LRFD/ASD combos + story drift (machine-precision validated); geotech liquefaction triggering (Seed-Idriss CSR + SPT/CPT CRR + Tokimatsu, Loma Prieta validated); multi-axial critical-plane fatigue — Findley, SWT-3D, Brown-Miller.

**Machine elements depth** ✅ — ISO 6336 gear rating Method B (safety factors ZH=2.495, ZE=191 √MPa validated); ISO/TS 16281 bearing aISO modified life (Lnm, contamination + misalignment); planetary gearbox (3 Willis modes + compound, torque identity to 1e-10); multi-axial fatigue folded in.

**Thermo-fluid depth** ✅ — IAPWS-IF97 steam properties Regions 1/2/4 validated to <1e-3 vs reference tables; Bell-Delaware shell-and-tube HX (full TEMA layout + 5 correction factors + ΔP both sides, Kern U≈504 validated); transient pipe-network (MOC waterhammer + quasi-steady + surge-tank); ASHRAE CLTD/RTS transient cooling loads (Sol-air + fenestration, ASHRAE Ch. 18).

**Electronics / power depth** ✅ — IBIS-AMI signal integrity (IBIS 5.1 parser + Bergeron channel + PRBS eye envelope); AC PDN impedance sweep + target-Z + decap optimiser; AC load-flow Newton-Raphson polar-form (3+5-bus validated); protection coordination IEC 60255 U1-U5 + IEEE C37.112 + IEEE 1584-2018 arc-flash incident energy; photonics fibre-optic link budget.

**Aero / marine / space depth** ✅ — 3D VLM with viscous strip drag + Prandtl-Glauert/Kármán-Tsien compressibility + Korn-Lock wave-drag (PG 1.401× exact); strip-theory seakeeping RAOs (Lewis-form STF + JONSWAP, Wigley validated); Holtrop-Mennen naval resistance + EHP; multi-revolution Lambert (Lancaster-Blanchard / Izzo 2015, sub-mm propagation residual N=1/N=2); 6-DOF flight dynamics + ADCS test stand.

**Manufacturing depth** ✅ — adaptive/trochoidal CAM HSM (iterative offset + 50 % trochoid overlap, engagement on target) + rest machining (grid-based uncleared region); Taylor extended tool-life model (vcT^n·f^a·dp^b=C) + Gilbert economic speed; moldflow Hele-Shaw front tracking + weld-line detection + air-trap prediction; casting shrinkage table + Chvorinov solidification + riser sizing + gating design; NFP true-shape polygon nesting (Minkowski-sum + IFP + bottom-left fill, 57.6 % L-shape utilisation); sheet-metal bend table (K-factor/BD/spring-back per material/thickness).

**Verticals depth** ✅ — dental anatomic crown (multi-cusp fan construction, not placeholder cylinder); horology Swiss lever escapement + mainspring barrel + balance-wheel oscillator (isochronism correction); solar PV partial shading + bypass-diode IV + global MPPT + mismatch loss (60-cell P=255 W validated); Bell-Delaware HX (D4 + D13 overlap).

**Tolerancing / QA depth** ✅ — 3D vector-loop tolerance stackup (6-DOF Jacobian sensitivity, `tolstack/tol3d.py`); SPC control charts (Shewhart/CUSUM/EWMA + Nelson/WECO run rules, `spc/charts.py`); ISO 286 limits & fits consolidated.

**Optics / acoustics depth** ✅ — Gaussian beam propagation (complex-q + ABCD + M² + fibre coupling, HeNe zR=4.96 m validated, ISO 11146-1); non-sequential ray tracing with Fresnel-split traversal + ghost detection (0.01 % ghost fraction validated); wave-domain room acoustics — image-source IR + Schroeder RT60 + modes + SEA (3.1 % error vs Sabine); Seidel S5 corrected (was zero).

**Implicit geometry** ✅ — extended TPMS / lattice library: FRep CSG ops (union/intersect/subtract/blend/shell) + implicit domain warps (twist/taper/wave) added to `kerf_cad_core.frep.csg`.

**Silicon** ✅ — analog PVT corner simulation: 60 corners (5 process × 3 voltage × 4 temperature) + Monte-Carlo mismatch per corner; bandgap ±31 mV, Pelgrom σ matched (`silicon/analog/pvt.py`).

**Materials + LCA** ✅ — Ashby database expanded to ~200 materials (14 families) with Pareto frontier multi-objective selection (`matsel/multi_objective.py`); full ISO 14040/44 LCA (4 phases: cradle/use/transport/EoL; impact categories: GWP/AP/EP/HTP/water/PM2.5 + Monte-Carlo uncertainty, `kerf-lca/phases.py`).

**Modelica / DAE** ✅ — system-simulation component library expanded to 16 components spanning mechanical / hydraulic / pneumatic / thermal / control.

**Compare matrices** ✅ — structured feature-matrix YAML added for 14 reference CADs: Fusion 360 (+55 rows), SolidWorks (+52), Onshape (+56), FreeCAD (+61), Rhino (+50), KiCad (+39), CATIA (+52), Creo (+54), NX (+54), Inventor (+53), AutoCAD (+41), Altium (+41), Revit (+41), Blender (+42) — 741 grounded rows total, sourced to vendor documentation.

**Landing / SEO** ✅ — persona-led marketing funnel restructure (14 sections, all 25 illustrations rendered); SEO meta (title/description/OG/Twitter/JSON-LD SoftwareApplication schema).

**Domain pages** ✅ — all 23 per-domain pages now have hero illustrations and capability illustrations wired in via `DomainPage` `heroIllustration` + `capabilityIllustrations` props (new vitest coverage).

**Security hardening** ✅ — `/run-topo` route now requires auth (`Depends(require_auth)`); NFP `grid_step` clamped to prevent resource exhaustion; PVT `n_mc` clamped; silicon synthesis blocks Yosys module-name injection.

**Infra refactor** ✅ — extracted shared `_guard_*` input-validation helpers into `kerf_cad_core._guards` module; applied across 68 files (−2009 / +129 lines net).

### Latest delta (2026-05-19)

What landed in the 24 h ending 2026-05-19. All items ✅ as of this sync.

**Silicon Phase 1 + 2 + 3** ✅ — `kerf-silicon` package, T-231..T-248:
VHDL parser (`kerf_silicon.hdl.vhdl`) + Verilog parser (`kerf_silicon.hdl.verilog`);
GHDL simulation bridge + Yosys synthesis bridge + ngspice bridge;
GDS II / OASIS I/O (`kerf_silicon.gds`); interactive layout viewer wired in the frontend;
SKY130 PDK integration (`kerf_silicon.pdk.sky130`);
LEF macro reader + Liberty timing/power reader;
OpenROAD bridge (place-and-route, floorplan, clock-tree synthesis);
design-rule check engine (`kerf_silicon.drc`);
layout-vs-schematic (LVS) runner;
parasitic RC extraction (`kerf_silicon.extraction.parasitic`);
mask-fracturing pipeline (`kerf_silicon.fracture`);
LLM tool surface for all twelve capabilities.

**Firmware** ✅ — `kerf-firmware` package, T-225..T-230:
board catalogue (`boards.json` — Arduino, ESP32, STM32, RP2040, AVR families);
library cache with `platformio lib` pass-through;
direct-gcc orchestrator (`build.py` — `avr-gcc` / `arm-none-eabi-gcc` / `xtensa-esp32-elf`, graceful sentinel when absent);
upload wrappers (`avrdude` / `openocd` / `esptool`);
serial monitor panel (`FirmwareView.jsx` — build log + live serial output);
LLM tool surface (`build_firmware`, `flash_firmware`, `monitor_serial`).

**Aerospace** ✅ — `kerf_cad_core.aero` + `kerf_cad_core.composites` + `kerf_cad_core.matsel`:
VLM / panel-method lift and induced-drag (`thin_airfoil` + `finite_wing`);
aeroelastic flutter boundary (Theodorsen, strip theory);
6-DOF rigid-body dynamics (`dynamics/six_dof.py`);
orbital mechanics (Kepler, Lambert, Hohmann — `aero/orbital.py`);
propulsion (actuator-disc, Breguet range/endurance);
composites depth — Classical Lamination Theory: ABD matrix, ply stress/strain,
Tsai-Wu / max-stress / Hashin failure indices, first-ply-failure, laminate moduli;
materials database (`matsel`) — Ashby-ranked engineering material selector,
55+ seeded materials (metals, polymers, composites, ceramics);
ADCS (attitude-determination + control system tools);
thermal network solver (`thermalcut`);
LLM tool surface for all aerospace capabilities.

**Frontend wire-ups landed this session** ✅:
- Viewport: Render dropdown (replaces scattered toggles), Daylight mode (strong sun + crisp shadows), standalone Exposure slider (commit `7327e7e`)
- Shadow controls (PCF soft-shadows, shadow-map resolution picker)
- Quality presets (Low / Medium / High / Ultra — adjusts shadow maps, MSAA, bloom)
- Material editor panel (roughness / metalness / opacity / emissive + per-material PBR preview)
- Viewport keybindings (numpad preset views, F-key focus, orbit/pan/zoom keyboard parity)
- Firmware actions wired in file-tree context menu (Build / Flash / Monitor for `.ino` / `.c` / firmware kinds)
- GDS layout viewer (`GDSView.jsx` — layer palette, zoom/pan, net highlight, DRC overlay)
- Monaco editor modes: VHDL (`.vhd`), Verilog (`.v`), SPICE (`.sp` / `.cir`) syntax highlighting
- cmd-K sector palette: Aerospace / Firmware / Silicon sectors surfaced in the quick-open command palette
- Orbit viewer (`OrbitViewer.jsx` — orbit propagation plot, ground track, pass predictor)
- Attitude viewer (`AttitudeViewer.jsx` — 3D spacecraft attitude with quaternion / Euler display)
- Thermal network viewer (`ThermalNetworkView.jsx` — node/edge resistance graph + steady-state temps)
- Airfoil polar plot (`AirfoilPolarPlot.jsx` — Cl vs α, Cd vs Cl, L/D vs α from `kerf_cad_core.aero`)
- FEM result viz: deformed-shape overlay + von-Mises / principal-stress contours (wired to `kerf-fem` result JSON)
- CFD streamlines: 2-D streamline overlay on potential-flow and Navier-Stokes results (`CFDStreamlineView.jsx`)
- Sector tour: guided intro overlay for Aerospace, Firmware, and Silicon sectors

### Platform / infra
- **Auth + projects + files + chat (CRUD)** ✅ — Postgres, JWT, Google OAuth.
- **Plugin monorepo (`packages/kerf-*`)** ✅ — `kerf-core` app factory +
  entry-point loader; ~25 plugin packages; persona extras; 864+ tests.
- **Single-binary build + brew/curl install** ✅ — embedded Vite SPA (~32 MB).
- **Auth-optional local mode** ✅ — `POST /auth/bootstrap-local` singleton user.
- **Cloud: workshop sharing, Paystack billing, LiteLLM pricing, free/paid
  buckets + wallet** ✅ — USD-display/ZAR-settle, BYO-key plumbing dormant.
- **Cloud: fly.io + Tigris deploy** ✅ — primary JNB, worker fleet.
- **Cloud: git (commits/branches/merge/GitHub sync) + S3 git Storer** ✅.
- **Large-file git handling** ✅ — `.step-ref` pointer kind, Phase 1.
- **Diff-based + compressed revisions** ✅ — 82× shrink.
- **Workspaces (orgs), activity timeline, avatars/CDN, collapsible chat** ✅.
- **E2E Playwright + per-plugin pytest suites** ✅.
- **Hosted-billing ledger schema on fresh databases** ✅ — billing-ledger
  schema fix so the hosted billing path stands up correctly on a
  brand-new database (landed this session).
- **Testing / seeding / deploy-hardening initiative** 🚧 — broader test
  suites + realistic seed data + one-command local/dev loops; partially
  landed, the remainder is the P0-8 quality gate (§3).

### Scripting / SDK
- **`.script.py` via `kerf-sdk`** ✅ — `/v1/rpc` JSON-RPC over the LLM tool
  registry; API tokens; PyPI publish. → `docs/llm/script.md`.
- **SDKs: Python · TypeScript · Rust · Go · Lua** ✅ — same `/v1/rpc` wire
  format across all five.

### Parametric core
- **Equations / global parameters** ✅ — `.equations`, mathjs.
  → `docs/llm/equations.md`.
- **Configurations / variants** ✅ — per-file param overrides, BOM rollup.
  → `docs/llm/configurations.md`.
- **Materials database** ✅ — `.material` kind, 55 seeded materials.
- **Two coexisting kernels** ✅ — `.jscad` (mesh) + `.feature` (OCCT BRep),
  shared `.sketch`/`.assembly`/`.drawing`. A **third, pure-Python B-rep +
  NURBS kernel** (`packages/kerf-cad-core/src/kerf_cad_core/geom/`) now
  produces validated `Body` topology, tolerant booleans, G1/G2 fillets,
  closest-point, hardened SSI, and a parametric history DAG with
  persistent face naming — usable without OCCT. See **Geometry kernel —
  depth** below and `docs/plans/geometry-kernel-roadmap.md`.

### Geometry kernel — depth

<!-- Status reconciled 2026-05-17: P0 + P1 (5 streams) + P3 keystone landed in
     packages/kerf-cad-core/src/kerf_cad_core/geom/. Plan + per-task checklist
     in docs/plans/geometry-kernel-roadmap.md. P2 (pure-Python STEP/IGES +
     SubD↔NURBS + mesh→NURBS autosurface + 2D region boolean) = next focus.
     Test count is verified via `pytest --collect-only`, not estimated. -->

The pure-Python geometry kernel jumped from *Rhino-width construction
verbs but no topology binding and no closest-point* to a real
math-depth moat. Detail + per-task checklist in
[`docs/plans/geometry-kernel-roadmap.md`](./docs/plans/geometry-kernel-roadmap.md).
Quick map of what is in `packages/kerf-cad-core/src/kerf_cad_core/geom/`:

- **B-rep topology keystone** ✅ — `brep.py` (1 312 LOC): radial-edge-ish
  `Body → Solid → Shell → Face → Loop → Coedge → Edge → Vertex` hierarchy,
  nine Euler operators with exact inverses, generalised Euler–Poincaré
  invariant *enforced and re-checked*, six-point `validate_body`. Contract
  frozen in `geom/BREP_CONTRACT.md`.
- **Build bridge** ✅ — `brep_build.py` (833 LOC) — analytic verbs (box /
  cylinder / sphere / Coons patch) emit a `validate_body`-clean `Body`;
  every public constructor ends with an internal `validate_body` assertion.
- **Tolerant pure-Python solid booleans** ✅ — `sew.py` (386 LOC) +
  `boolean.py` (1 195 LOC). Face-imprint via SSI, tolerance-monotonic
  vertex/edge merge, regularised cut / fuse / common over the primitive
  matrix; result is `validate_body`-clean and 2-manifold. No OCCT required.
- **G1 / G2 surface blend + edge fillet + chamfer** ✅ — `fillet_solid.py`
  (1 631 LOC) + `chamfer.py` (1 040 LOC). Rolling-ball trim+sew on
  planar+planar and planar+cylindrical edge contracts; constant /
  asymmetric / variable-width chamfer; G2 cross-sections with verified
  curvature continuity.
- **Surface + curve + loop offsets** ✅ — `offset.py` (877 LOC) — exact-
  distance offsets with self-intersection trim; analytic oracles
  (concentric circle, parallel plane, sphere r→r+d).
- **Coons patches** ✅ — `coons.py` (519 LOC) — boundary interpolation
  exact to `1e-12`.
- **Closest-point / point-inversion** ✅ — `inversion.py` (629 LOC).
  Foundational primitive for snapping, projection, deviation, SSI seeding,
  fitting, draft analysis. Piegl 6.1 with analytic first + second partials
  on rational surfaces.
- **Hardened SSI** ✅ — `intersection.py` rebuilt with loop-detection,
  tangential-branch detection, small-loop guard, analytic line/quadric
  specialisations; rational-weight bug fixed.
- **Parametric history DAG with persistent face/edge naming** ✅ —
  `geom/history/` (1 962 LOC across `feature.py`, `persistent_naming.py`,
  `dag.py`, `evaluators.py`). Three-part `feature_id::role::fingerprint`
  selectors. Edit a box parameter ⇒ a downstream fillet still targets the
  semantically same edge, not a different one. Box / cylinder / sphere /
  boolean / chamfer / fillet evaluators wired.
- **Ship-gate kernel tests, all green** ✅ — verified by `pytest
  --collect-only` on the listed files (2026-05-17): `test_brep_topology`
  51, `test_euler_invariants` 63, `test_brep_build` 43,
  `test_boolean_solid` 36, `test_chamfer` 30, `test_fillet_blend_g2` 53,
  `test_offset` 33, `test_coons` 49, `test_surface_analysis_refvalues` 46,
  `test_nurbs_correctness` 44, `test_inversion` 42, `test_ssi_robust` 37,
  `test_curve_toolkit_exact` 46, `test_history_dag` 47 — **620 hermetic
  analytic-oracle-asserted tests**. Full repo collection: 23 902 tests.
- **P2 next** 🚧 — pure-Python STEP AP203/214 reader/writer (decouple
  interop fidelity from OCCT); SubD ↔ NURBS watertight `Body` bridge;
  mesh → NURBS autosurface to a deviation tolerance; 2D region boolean
  on planar loops (sketch-driven solids without OCCT round-trip).

### Render output

- **PBR hero / share-card pipeline** ✅ — `captureHeroShot`
  (`src/lib/heroShot.js`) at 2048×2048 4× supersample, ACES tonemap,
  PMREM-pre-filtered RoomEnvironment HDRI, `UnrealBloomPass`; wired
  into `src/components/Renderer.jsx` so Workshop covers, share-cards,
  and the primary 3D viewport share one production-grade lighting path.
- **Blender Cycles offline path** ✅ — render-quality output for jewelry
  via the existing `kerf-render` worker.
- **Honest gaps** — **caustics + dispersion solver** (T-106) is 🔴 not
  started; we have PBR + HDRI + bloom but no Cycles / V-Ray / Enscape /
  KeyShot-class caustic transport or gem-dispersion ray-trace.

### Frontend / UX

- **Pre-React boot loader** ✅ — Kerf-branded SVG triangles loader
  injected in `index.html` paints immediately, then transitions cleanly
  into the first React route. Backed by `src/components/Loader.jsx` +
  `src/components/RouteFallback.jsx` so route-level Suspense fallbacks
  share the same visual language. Vitest smoke coverage.
- **Docs viewer redesign** ✅ — grouped sidebar (domains + workflows +
  cloud + reference + develop), breadcrumbs, TOC, audit-filter,
  internal-planning-artifact filtering. `scripts/build-docs-manifest.mjs`
  emits the grouped taxonomy into `public/docs-manifest.json`.
- **Docs viewer article-rendering fix** ✅ — article body now renders
  correctly in the user-facing docs viewer (landed this session).
- **Comparison pages** ✅ — `src/routes/compare/` ships **14**
  head-to-head pages: Altium, Autocad, Blender, Civil3d, Freecad,
  Fusion, Inventor, KiCad, MatrixGold, Max3ds, Onshape, Revit, Rhino,
  Solidworks (plus a singleton drafting card, 14 comparison routes wired
  in `src/App.jsx`). Freecad / KiCad / Rhino / Revit / Fusion were
  deepened; Altium / MatrixGold / Blender / Onshape / Solidworks /
  Autocad / Civil3d / Inventor / Max3ds are new.
- **Compare hub with per-category feature matrices** ✅ —
  `src/routes/compare/index.jsx` + `src/routes/compare/CategoryMatrix.jsx`
  render Mechanical / Electronic / BIM / Jewelry & NURBS / DCC matrices
  with per-CAD cards (5 mechanical + 2 electronic + 2 BIM + 2 jewelry +
  2 DCC + 1 drafting).
- **Scroll-to-top on route change** ✅ — `src/components/ScrollToTop.jsx`
  wired in `src/App.jsx` (was: landing on `/compare` mid-scroll).
- **Roadmap link in public topbar** ✅ — `NAV_LINKS` in
  `src/components/Header.jsx` now exposes `/roadmap` alongside Docs and
  Compare.
- **Body max-width h-scroll guard** ✅ — `body { max-width: 100vw }` +
  `overflow-x: clip` on html/body/#root in `src/index.css` (defensive
  CSS that makes site-wide horizontal scroll physically impossible on
  Safari/WebKit); Landing.jsx hero wrapper now clips.
- **Touch + responsive polish** ✅ — Renderer + Gumball touch gestures,
  Editor responsive layout, top-bar overflow, Docs mobile drawer.

### Mechanical / CAD
- **OCCT `.feature` Phase 2/3** ✅ — Pad/Pocket/Revolve/Hole/Fillet/Chamfer/
  Shell/Sweep1-2/Loft/Push-Pull/RotateFace/Linear-Polar-Mirror patterns;
  face/edge gumball direct modeling.
- **PartDesign + sketch→3D shortcuts** ✅ — helix/draft/mirror/rib/multi-
  transform; boss_with_draft, cut_from_sketch, hole_pattern_from_sketch,
  loft-symmetric, sweep1-mode. → `docs/plans/freecad-sketch-shortcuts.md`.
- **2D sketcher (planegcs) v1 + v2** ✅ — full constraint set, trim/extend,
  ellipse, B-spline, bezier, fillet, mirror, patterns, symmetry-over-line.
- **Sketch → JSCAD workflow** ✅ — reactive re-eval.
  → `docs/plans/sketch-to-jscad.md`.
- **Assembly model + 3D mates (Tier 0)** ✅ — coincident/concentric/parallel/
  perp/distance/angle/tangent; gradient-descent solver.
- **Tolerance stack-up** ✅ — worst-case/RSS/Monte-Carlo + auto chain-walk.
- **2D drawings (TechDraw-flavored)** ✅ — multi-sheet, dimensions, GD&T
  frames, section hatching, leaders/balloons, centerlines, snap.
- **NURBS surfacing (Phase 4)** ✅ — sweep1/2/network/blend/loft +
  `surface_continuity` (C0–C2/G0–G2) + Capability 1 robust surface-direct
  boolean (`feature_surface_boolean`) + Capability 2 trim-by-curve
  (`feature_trim_by_curve`) + Capability 4 curvature-comb viz
  (`feature_surface_curvature_combs`) + zebra / reflection-line viewport
  toggle (shader-side, no WASM rebuild). Algorithmic G3 deferred (stock
  OCCT structurally cannot enforce `GeomAbs_G3`).
  → `docs/plans/nurbs-phase-4-full.md`, `nurbs-booleans-v1.md`.
- **Rhino parity** ✅ — 3DM I/O, SubD (Catmull-Clark), quad remesh, mesh
  tools, layers/display, parametric `.graph`, render output, curve depth,
  drafting completeness.
- **Persistent face naming** ✅ — sketch-anchored + topo-hash (frontend
  T1–T2 + boolean hardening T3 shipped) **plus** a kernel-side
  `feature_id::role::fingerprint` selector now wired into the pure-Python
  parametric DAG (`geom/history/persistent_naming.py`) so a downstream
  fillet/chamfer survives an upstream parameter edit.
  → `docs/plans/persistent-face-naming.md`,
  `docs/plans/geometry-kernel-roadmap.md`.

### Simulation / manufacturing
- **FEM** ✅ — FEniCSx (+ CalculiX) linear-static + modal (SLEPc) + steady
  thermal + bonded contact; deformed-shape overlay. *Verified enum:
  `linear_static | modal | thermal` only.*
- **FEM reference-value suite** ✅ — `kerf_fem.pressure_load` shipped;
  43-test `test_fem_refvalues.py` with citable Roark / Blevins /
  Incropera oracles (42 green, one ASTM E1049 rainflow test skipped —
  real bug flagged in `fatigue_fem._rainflow`, tracked under T-100).
- **CFD foundation (2-D laminar scope)** ✅ — `kerf_fem.cfd_potential`
  (potential flow, `Cp(θ) = 1 − 4 sin²θ` analytic oracle) +
  `kerf_fem.cfd_navier_stokes` (lid-driven cavity, Ghia Re=100
  reference); 61 hermetic CFD tests in
  `packages/kerf-fem/tests/test_cfd.py`. Full CfdOF parity (turbulence
  k-ε / k-ω SST, 3-D unstructured meshing, OpenFOAM bridge) stays
  in flight under T-101.
- **Topology optimization** ✅ — SIMP via FEniCSx, NURBS surface fit, multi-body.
- **CAM** ✅ — 2.5D + 3D parallel/waterline + lathe + **5-axis** constant-tilt
  + 3+2 indexed; tool DB (7 types); LinuxCNC/GRBL/Mach3/Fanuc posts.
  → `docs/plans/5-axis-cam.md`.
- **Slicing** ✅ — plane-section, CNC layered, 3D-print G-code (Cura, Tier 1).

### Electronics (design-side — fab output is P0-1)
- **tscircuit `.circuit.tsx`** ✅ — schematic/PCB/3D-board render, edit helpers.
- **KiCad-class design** ✅ — ERC, hier-schematic, buses/diff-pairs, net
  classes/rules, length tuning, via stitching/teardrops, shove router,
  pad mask/paste overrides, copper pour, layer stack, DRC overlay.
- **SPICE + RF + autorouting** ✅ — ngspice (`/run-spice`), scikit-rf
  S-params/Smith chart, FreeRouting DSN/SES.
- **Wiring/harness `.wiring`** ✅ — WireViz YAML→SVG (2D only; 3D = P1-7).
- **PLC `.plc.st`** ✅ — MATIEC lint Tier 1.
- **Silicon / IC layout (kerf-silicon)** ✅ — VHDL + Verilog parsers; GHDL
  simulation bridge; Yosys synthesis bridge; ngspice bridge; GDS II / OASIS I/O;
  interactive GDS layout viewer; SKY130 PDK integration; LEF macro + Liberty
  timing/power readers; OpenROAD place-and-route bridge; DRC engine; LVS runner;
  parasitic RC extraction; mask-fracturing pipeline; LLM tool surface. T-231..T-248.
- **Firmware / embedded** ✅ — `kerf-firmware`: board catalogue (Arduino / ESP32 /
  STM32 / RP2040 / AVR); library cache; direct-gcc orchestrator (`avr-gcc` /
  `arm-none-eabi-gcc` / `xtensa-esp32-elf`); upload wrappers (`avrdude` /
  `openocd` / `esptool`); serial monitor panel (`FirmwareView.jsx`); LLM tools
  (`build_firmware`, `flash_firmware`, `monitor_serial`). T-225..T-230.

### Aerospace / composites
- **Applied aerodynamics** ✅ — `kerf_cad_core.aero`: ISA standard atmosphere,
  dynamic pressure, Reynolds / Mach, Prandtl-Glauert, thin-airfoil Cl/Cm,
  finite-wing lift-slope / CL / induced drag, L/D + best-glide, level-flight
  thrust/power, stall speed, climb rate, actuator-disc thrust, propeller ideal
  efficiency, Breguet range + endurance. Ten LLM tools registered.
- **Composites (CLT)** ✅ — `kerf_cad_core.composites`: reduced stiffness Q,
  transformed Q̄(θ), ABD matrix, laminate response (mid-plane ε/κ from N/M),
  per-ply stress/strain, failure indices (max-stress / Tsai-Wu / Hashin), laminate
  Ex/Ey/Gxy/ν, first-ply-failure load scaling. Seven LLM tools registered.
- **Materials selector (Ashby-style)** ✅ — `kerf_cad_core.matsel`: property
  database for 55+ engineering materials; filter + rank by strength/weight/cost/
  thermal; `select_material` LLM tool returns top candidates with rationale.

### Architecture / BIM
- **`.bim` text-DSL → IFC4** ✅ — walls/slabs/spaces/openings/levels/site;
  → `packages/kerf-bim/llm_docs/bim.md`.
- **IFC import Tier 1** ✅ — walls/slabs/spaces/levels/sites only.
- **Revit parity** ✅ — `.family`/`.schedule`/`.view`/`.sheet`, categories,
  type-vs-instance, phasing/filters, stairs/railings, MEP, curtain wall.

### Library / parts / BOM
- **Library system v1 + BOM** ✅ — `kind='part'`, distributor APIs (DigiKey/
  Mouser/LCSC), curated manufacturer libs, library split from workshop.
- **Cross-project parts (PCB-as-part)** ✅ — external_ref, lockfile,
  derived-artifact cache. → `docs/llm/cross_project.md`.
- **kerf-parts** ✅ — MIT-clean fetch/convert pipeline; kicad + freecad-library
  + bolts adapters all complete with tests (`test_bolts_freecad_adapters.py`,
  `test_kicad_adapter.py`).
- **kerf-partsgen** ✅ — author-once-then-enumerate standard-parts generator
  framework; 5 family generators shipped (ISO 4017 hex bolt, ISO 7089 flat
  washer, ISO 4762 socket-head cap screw, ISO 4032 hex nut, DIN 125 plain
  washer).

### Imports
- **KiCad** ✅ (Tier 1+2 — sch/pcb + symbol/footprint libs) ·
  **FreeCAD** ✅ (Tier 1+2) · **OpenSCAD** ✅ · **Rhino 3DM** ✅.
- **LLM tool consolidation** ✅ — small fixed surface + `search_kerf_docs`
  over `packages/kerf-chat/llm_docs/`.

---

## §4.5 — Honest depth gaps tracked (2026-05-17)

Concrete, near-term capability gaps surfaced from a head-to-head pass
against the reference tool in each sector. Each line maps to a `T-NN` in
[`tasks.md`](./tasks.md) so the loop can pull them; status here mirrors the
task. These are **not new sectors** — they are depth gaps inside sectors
already shipped or in-flight. Listed in roughly the order they convert
evaluators today.

| # | Gap | vs | T-NN | Status |
|---|---|---|---|---|
| G-1 | **FEM matching CalculiX / Z88 / Mystran depth** — nonlinear, explicit, acoustics, EM, fatigue beyond the verified linear-static+modal+thermal slice. Reference-value suite (`pressure_load.py` + 43-test Roark/Blevins/Incropera oracles, 42 green, rainflow bug flagged) landed this session; full nonlinear/explicit/acoustics/EM/fatigue wiring still ahead. | CalculiX / Z88 / Mystran | T-100 | 🚧 in flight |
| G-2 | **CFD (CfdOF-class)** — beyond `cfd_potential` / `cfd_navier_stokes` (2-D laminar foundation now landed with 61 hermetic tests) to turbulence models, 3-D unstructured meshing, OpenFOAM bridge | CfdOF / OpenFOAM | T-101 | 🚧 in flight |
| G-3 | **Interactive push-and-shove diff-pair tuning** — Kerf has length tuning only; KiCad has interactive push-and-shove | KiCad / Altium | T-102 | 🔴 not started |
| G-4 | **Broader ECAD import** — Allegro / PADS / gEDA / Eagle v10 (today only KiCad-oriented) | Altium / Cadence | T-103 | 🔴 not started |
| G-5 | **Kernel G3 / NURBS Phase 4 trim-by-curve + class-A leading** — G3 curvature combs partially shipped (#100); imprint + leading still to go | Alias / ICEM Surf | T-104 | 🚧 in flight |
| G-6 | **SubD authoring with creases + edit workflow** — `subd.py` + quad-remesh shipped; no creation / edit / crease workflow | Rhino 8 SubD | T-105 | 🔴 not started |
| G-7 | **Render: caustics + dispersion** — PBR + HDRI + bloom shipped this session; T-106 split into T-106a..f: backend Blender Cycles (spectral dispersion + caustics) for hero output + in-browser `three-gpu-pathtracer` for free preview / offline. Self-host docker worker + GPU-second metering into `kerf_paid` | Cycles / V-Ray / KeyShot / Enscape | T-106 (a..f) | 🔴 not started |
| G-8 | **Direct + parametric history coexistence** — Kerf is feature-tree primary; limited direct editing alongside | Fusion / Inventor / Onshape | T-107 | 🔴 not started |
| G-9 | **Full joint system** — rigid / revolute / slider / cam / gear / pin-slot; `kerf-mates` ships a constraint solver but fewer joint types | Inventor / SolidWorks / Onshape | T-108 | 🔴 not started |
| G-10 | **BIM parametric family system** — no native family-authoring UX yet (Tier-2 family *import* shipped) | Revit | T-109 | 🔴 not started |
| G-11 | **BIM family library** — no shipped curated catalog | Revit | T-110 | 🔴 not started |
| G-12 | **BIM walls / doors / windows / slabs full parametric** — basic primitives only | Revit | T-111 | 🔴 not started |
| G-13 | **BIM stairs / ramps full** — basic stairs only | Revit | T-112 | 🔴 not started |
| G-14 | **BIM structural grid + framing** — early today (Revit Structure / Robot / Tekla class) | Revit Structure / Robot / Tekla | T-113 | 🔴 not started |
| G-15 | **BIM site / earthwork (toposolids)** — basic only | Revit / Civil 3D | T-114 | 🔴 not started |
| G-16 | **BIM material catalogue with render appearance** — PBR shipped, no BIM-bound material library | Revit / Enscape | T-115 | 🔴 not started |

---

## §5 — Deliberately NOT building (and why)

This list is **only** AI-redundant *authoring/UX interaction paradigms*. It
is **not** a list of skipped domains or skipped correctness features.

| Not building | Why (AI-native rationale) |
|---|---|
| Visual node programming (Grasshopper / Dynamo / Sverchok) | The LLM writing a parametric script *is* the graph. `.script.py` + the SDKs + JSCAD + the `.graph` data model already cover the value. |
| Ribbon / toolbar / command-palette maximalism | The LLM **is** the command palette — discovery is a chat sentence, not a menu hunt. |
| Macro recorders / scripting-GUI builders | The LLM **is** the macro author; it writes `.script.py` directly. |
| Gumball / direct-modeling maximalism | Keep a *basic* gumball; the LLM edits the feature tree. No need for the deep direct-modeling command surface. |
| In-app wizards / tutorials / onboarding tours | The chat **is** the wizard — context-specific guidance on demand. |

**Hard guardrail (restated):** this skip-logic applies *only* to
authoring/UX mechanisms. It **never** applies to (a) sectors/domains — all in,
see §2/§3 — or (b) correctness / output / standards features (GD&T,
Gerber/fab output, DWG handoff, verification/self-check), which are *more*
important under an LLM, not less.

---

## §6 — Long-term horizon (sectors — directional, NO tasks)

**Directional only.** Every sector here is fully **committed** ("we do
everything"), but it is deliberately **not** broken into [`tasks.md`](./tasks.md)
tasks until it is promoted to near-term P0/P1. This is the explicit parking
lot for sectors with **low near-term fit but high long-term value** —
distinct from P3, which already enumerates near-term-reachable long-tail
verticals. A sector graduates from §6 when an existing-persona credibility
need or a strategic bet pulls it forward; at that point it gets a P-tier line
in §3 and sized tasks in `tasks.md`.

| Sector | Reference tools | Long-term fit rationale | Status |
|---|---|---|---|
| **Textiles / apparel & technical-textile pattern-making** | CLO3D, Optitex, Gerber | One of the largest design workforces on earth. Needs a distinct 2D-pattern + cloth-drape engine; pattern-making is parametric (good eventual AI-fit), cloth drape simulation is the genuinely hard part. | 🔴 not started |
| **Composites engineering** | Fibersim, CATIA Composites | Ply-book / laminate / draping / fiber-steering. Spans aerospace, automotive, wind, and marine — high value, but a specialized layup engine. **Classical Lamination Theory analysis shipped** (`kerf_cad_core.composites` — ABD matrix, ply stress/strain, Tsai-Wu/max-stress failure indices, first-ply-failure, laminate engineering moduli, LLM tool surface). Remaining: ply-book authoring UX, draping simulation, fiber-steering, Fibersim-class depth. | 🚧 in flight |
| **Medical / patient-specific** | Materialise Mimics / 3-matic | DICOM → surgical guides / orthotics / implants. High societal value and fast-growing; needs a medical-imaging-to-geometry pipeline. | 🔴 not started |
| **Process plant & pressure vessels** | AVEVA E3D, PV Elite, ISOGEN | Spec-driven piping / isometrics + ASME BPVC / PD5500 vessels. Huge industrial footprint; rule-native (good long-term AI-fit). | 🔴 not started |
| **Optical / photonics** | Zemax, PIC tools | Lens design + integrated optics. Math / parametric substrate → very AI-native long-term once the physics solvers exist. **Shipped:** `kerf_cad_core.optics` — lensmaker, thin-lens / mirror / two-lens / Gaussian-beam imaging, MTF; LLM tool surface. PIC (photonic integrated circuits) and nonlinear optics remain 🔴. | 🚧 in flight |

*Cross-reference (not duplicated here): civil sub-engines and marine /
naval-architecture hull fairing are already seeded at **P3 (§3)** because they
are nearer-term reachable; they are tracked there, not in this horizon table.*

---

## §7 — Hosted infrastructure (operational, not feature scope)

This section tracks decisions about *where* the hosted tier runs. It is
deliberately separate from §1.5 (which is about portability and self-host)
and from §3/§4 (which are about features). Self-host users never see any of
this — the open-source binary keeps running on a single Postgres + the
user's filesystem regardless of what we choose here.

### §7.1 — Fly.io → Koyeb (P0, 2026-05-24)

**Why.** Fly.io discontinued GPU instances. Cycles renders (and any future
GPU-accelerated workload — FEM acceleration, ML-driven feature
recognition, real-time tessellation) need a host that still sells GPU
time. Koyeb sells the full GPU ladder (RTX-A4000 $0.50/hr → H100 $2.50/hr)
in Frankfurt + Washington + Singapore, with per-second billing and the
same Docker-image deploy model we already use.

**Status.** 🚧 in flight — config + billing repricing in progress. See
[`tasks.md`](./tasks.md) §"Infrastructure migration — Fly → Koyeb"
(T-400…T-410).

**Pricing impact.** Koyeb COGS is 3-4× cheaper than the Modal/Replicate
rates currently baked into `kerf-render.pricing_meter`. We re-ground the
GPU rate table to Koyeb's actual hourly price and lift the GPU markup
from 20% → 35% to absorb per-second billing variance, storage egress and
the operational buffer (autoscale headroom, monitoring, cold-start). Net
result is a **2-3× drop in user-facing GPU render price** with healthy
gross margin retained — see [pricing.md](packages/kerf-pricing/llm_docs/pricing.md).

**Migration shape.**

1. Author `koyeb.yaml` mirroring `fly.toml` (same Dockerfile, same env
   var set, same Tigris S3 bindings — Tigris is external, keeps working).
2. Move secrets via `koyeb secrets create` (1:1 with `flyctl secrets set`).
3. Run release migrations as a Koyeb pre-deploy command (same content as
   today's `flyctl deploy` release_command).
4. Smoke-test `kerf-dev` on Koyeb in Frankfurt, cut DNS, decommission Fly
   app. **No code change required** — the engine is portable Docker.

**Break-even target.** With ~$120/mo fixed Koyeb spend (1× `large` engine
+ 1× `small` Postgres if we move off Neon) the hosted tier breaks even at
~30 Studio ($9) or ~5 Pro ($29) seats — independent of any GPU render
margin. GPU margin compounds break-even once render volume materialises.

**Self-host guarantee.** Nothing in this migration changes the
self-host story. Local binary continues to require only Postgres and the
user's filesystem; no Koyeb dependency leaks into the open-core path.

---

## §8 — Kernel parity vs every CAD (P1, 2026-05-24)

**Why.** The geometry kernel (`kerf_cad_core.geom`, ~60 modules) is the
spine every persona stands on. GK-01..GK-139 are landed, but a
four-agent survey of Kerf vs **all ~18 kernel-relevant CADs**
(FreeCAD, Fusion, SOLIDWORKS, Onshape, Inventor, CATIA, Creo, NX, Rhino,
MatrixGold, Blender, ZBrush, 3ds Max, SketchUp, ArchiCAD, Revit,
Vectorworks, AutoCAD) found a concrete, finite gap list. This section
commits to closing it. The benchmark bar is **Rhino 8 / OpenNURBS**
(NURBS + class-A), **Blender + ZBrush** (SubD + mesh + sculpt), and the
**Parasolid/ACIS-class** parametric MCAD tools (solids robustness).

**Survey headline (2026-05-24).** Two structural findings reshaped the
frontier:
1. **Much of the class-A math is already shipped but unwired.** G3 blends
   (`surface_blend_g3`, `blend_srf_g3`), the curvature-rate continuity
   oracle, the zebra/reflection-line analyser, the class-A acceptance
   harness (GK-64), and the global continuity audit (GK-138) all exist
   and are verified — but are not exported from `geom/__init__.py` or
   exposed via `surfacing.py`, so users cannot reach them. **`docs/plans/occt-phase4.md` is stale** where it calls G3 "unbuilt" — that
   doc predates Phase-5 completion. The highest-ROI work is *wiring*,
   not new math.
2. **The pure-Python solid boolean only handles axis-aligned primitives**
   (`geom/boolean.py` raises `BuildError("unsupported-input")` for
   NURBS-faced or non-axis-aligned solids; general CSG delegates to the
   OCCT worker). This is the one foundational kernel gap that blocks
   architectural wall/roof joins and general pure-Python CSG.

**Scope.** Tracked as the **`GK-P` (parity) series** in
[`tasks.md`](./tasks.md), grouped:
- **Wiring** (expose shipped class-A math — all small, do first).
- **Foundational kernel** (general solid boolean, MatchSrf G3, isophote/
  EMap, Stam limit-tangents + G1 at extraordinary SubD points, fractional
  creases, analytic surface derivatives + robust SSI).
- **Construction verbs** (loft guide-rails — flagged by 3 surveys —
  sheet-metal hem/jog/multi-flange, direct-edit non-planar + delete-face,
  weldment gussets/end-treatments, surface patch-from-points).
- **SubD / mesh** (multires displacement stack, SDF CSG + marching-cubes,
  sculpt brush engine, in-process isotropic remesh fallback, surface-snap
  retopo, LSCM UV unwrap, poke, extrude-along-curve).
- **Architectural geometry** (B-rep→2D auto-tessellate, roof / curtain-wall
  / corridor generators, wall compound-layer offset, hatch-fill +
  section-fill, toposolid B-rep).
- **Sketcher** (collinear constraint, ellipse solver entity, G2 continuity
  — all flagged by every MCAD survey).
- **Interop** (3DM write into `geom/io` with a read→write→read Hausdorff
  oracle).

**Explicitly NOT in this push** (documented non-goals, not gaps): general
NURBS×NURBS trim stays OCCT-worker-delegated (`occt-phase4.md §4`);
OCCT-side G3 comb *enforcement* is structurally impossible (`GeomAbs_G3`
absent from OCCT's enum) — pure-Python is the G3 path. Interactive
viewport UIs (assembly motion study, GD&T PMI placement, SubD cage
editor, Fusion-style T-spline sculpt) are real but are *UI* investments,
not kernel gaps — parked separately.

**Execution.** Agent build-loop: Sonnet agents pull `GK-P` items in
isolated worktrees, one task per commit, integrate by SHA, until the
series is drained — the same loop that cleared GK-01..GK-139. The single
hardest item (general solid boolean) may warrant Opus.

---

## How to contribute

Pick a task from [`tasks.md`](./tasks.md) (sized for a single isolated agent
run), or open an issue proposing a new P3 sector line. The roadmap states
*why* and *in what order*; `tasks.md` is the *how*. Keep them in sync: when a
priority moves here, move the corresponding tasks there.
