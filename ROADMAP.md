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

---

## §2 — Per-persona deliverable scorecard

<!-- Status reconciled 2026-05-17: ECAD fab output ✅; jewelry render ✅; mechanical sheet metal/weldments/GD&T ✅ (bend table T-4 now ✅); architecture IFC Tier 2 + family editor ✅; DXF read+DWG bridge ✅; general DXF writer ✅ (T-7 shipped; DWG via ODA external); compare hub w/ per-category matrices + 14 compare pages ✅; ScrollToTop + Roadmap topbar link ✅; FEM reference-value suite + CFD foundation (potential + Navier-Stokes) ✅; body max-width:100vw h-scroll guard ✅. -->
<!-- Planning session 2026-05-18: the platform-trust dimension (own-your-data / one client / easy self-host / portability) is now captured in §1.5 and threaded through the §3 tiers; it underpins, but does not change, the per-persona scorecard below. -->

Brutally honest. For each persona: the end deliverable they must ship, and
whether Kerf can produce it **text-natively today**.

Prioritization rationale = **AI-fit × societal importance × workforce size ×
Kerf-readiness** — this is why the P0 spine is electronics / mechanical /
drafting (high on all four today) and why civil, despite its high societal
importance, sits at P3: it is engine-gated, not low-value.

| Persona | End deliverable they must ship | Status | One-line gap |
|---|---|---|---|
| **Mechanical engineer** | Parametric solid part / assembly + a dimensioned, GD&T-toleranced drawing + STEP | 🚧 partial | Strong core (OCCT features, sketcher, assemblies+mates, tolerance stack-up, linear/modal/thermal FEM, 3/5-axis CAM, TechDraw-flavored drawings *with* GD&T frames). Sheet metal flange/unfold/flat-pattern shipped; weldments + GD&T-from-model callouts shipped. **General DXF writer shipped** (T-7; DWG via ODA external). Remaining gap: **bend table** (T-4). |
| **Electronic engineer** | A *manufacturable* PCB: schematic → routed board → **fab package** | ✅ can manufacture | KiCad-class design (ERC, hier-schematic, net classes, shove router, autoroute/freerouting DSN, length tuning, via stitching, SPICE, RF, copper pour, imports KiCad libs) + **Gerber RS-274X, Excellon drill, pick-and-place, fab BOM, IPC-2581, ODB++ zip bundle** (`kerf_electronics.fab`) + 3D board STEP export for MCAD-ECAD co-design. |
| **Architect** | Coordinated building model → IFC + construction-doc drawings | 🚧 partial | `.bim` text-DSL → IFC4 (walls/slabs/spaces/levels/site, MEP, stairs/railings, curtain wall, schedules/views/sheets) + IFC import **Tier 1 + Tier 2** (openings/MEP/families/schedules) + first-pass parametric family editor shipped. **General DXF writer shipped** (T-7; DWG via ODA external). Honest gaps vs Revit: **no native family-authoring UX** (T-109), no shipped family library (T-110), only basic wall / door / window / slab parametrics (T-111), basic stairs / ramps (T-112), early structural grid + framing (T-113), basic site / toposolid (T-114), no render-appearance BIM material catalogue (T-115); construction-doc detailing still pending. |
| **Civil engineer** | Survey/terrain → alignment/corridor → grading + plan-and-profile sheets | 🔴 cannot | Essentially **nothing** civil-specific. Needs *distinct engines* (geospatial CRS, TIN/terrain, alignment/corridor solver, hydraulics, earthwork, LandXML/IFC-4.3-infra) — not feature-adds on the B-rep kernel. In the roadmap at **P3** with each engine named honestly — highest raw societal importance (water/sanitation/roads, esp. developing world); engine-gated, hence P3 not low-value. |
| **Drafter** | Multi-sheet 2D production drawing, exchanged as DWG/DXF | 🚧 partial | TechDraw-flavored drawings shipped (multi-sheet, dimensions, GD&T frames, section hatching, leaders/balloons, centerlines). **DXF reader + DWG bridge + general DXF writer all shipped** (`kerf_imports.dxf`, `dwg/bridge.py`, `kerf_imports.dxf_writer`; R12 + R2004). DWG output via ODA external (`dwg_note()`). Remaining gap: construction-doc detailing. |
| **Jewelry CAD designer** | Rendered/printable ring or setting with stones placed and metal-weight/cost | ✅ can render | Full toolkit shipped and wired: `kerf_cad_core.jewelry.{gemstones,gem_seat,settings,ring,metal_cost}` — 7 cuts, prong/bezel/channel/pavé/channel/pavé, US/UK/EU/JP sizer + 7 shank profiles, casting-cost, FeatureView inspectors, PBR gem/metal viewport materials, casting/STL production export, preset/template library, findings, chain/bracelet. OCCT JS worker `op*` handlers fully wired (`opGemstone`/`opGemSeat`/`opJewelryProngHead`/`opJewelryBezel`/`opJewelryChannel`/`opJewelryPave`/`opRingShank`). |
| **Automotive engineer** | Class-A bodyside / component + DMU + supplier exchange | 🔴 cannot | Transfers: NURBS surfacing, FEM, 5-axis CAM, zebra/reflection-line viz (shader-side, viewport toggle). **General DXF writer shipped** (T-7; DWG via ODA external). Gaps: BIW stamping bend table (T-4), 3D harness (2D WireViz only), crash/NVH/CFD/durability (FEM is linear-static/modal/thermal only), full-vehicle DMU. See [docs/plans/automotive.md](./docs/plans/automotive.md). |
| **Education / maker / hobbyist** | A printable / CNC-able functional part, enclosure, or furniture piece + cut list | 🚧 partial | Largest reach + strongest mission (democratizing design); 3D-print slicing (`packages/kerf-slicing`, CuraEngine) + 3/5-axis CAM (`packages/kerf-cam`) shipped. Needs the simple-parametric + cut-list / flat-pack path polished and a clear on-ramp. |

---

## §3 — Priority triage

Ordered by **leverage**, not time. Automotive cross-refs preserved inline.

### P0 — credibility blockers

<!-- Status reconciled 2026-05-16: P0-1 ✅ (gerber.py/excellon.py/pnp.py/ipc2581.py/odbpp shipped); P0-3 🔴→🚧 (T-1/T-2/T-3 done, T-4 bend table not done); P0-4 ✅ (boolean hardening + faceNamingT3Booleans corpus shipped). -->
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
- **Ladder logic / PLC programming** (IEC 61131-3 Ladder Diagram) 🔴 —
  complements the already-shipped structured-text PLC support
  (`.plc.st`); rounds out the automation / electronics domain with the
  ladder-diagram representation alongside structured text.
- **Embedded / firmware programming + integrated toolchains** 🔴 —
  Arduino (`.uno`), C / C++, broader programming-language support, and an
  integrated compiler / toolchain set (board + toolchain management, build
  / flash). PlatformIO is the reference model. Builds directly on the P0-6
  broadened text/code file support once per-language depth is needed.

### P3 — long-tail verticals & distinct-engine domains

**Everything else, all committed, lowest priority.** This is the proof that
"we do everything." Each line is a real domain on the path; many reuse the
parametric/partsgen spine, a few need distinct engines (named explicitly).

**Mechanical / product:** plastics & injection-mold tooling 🔴 · casting /
forging / die design 🔴 · packaging / dieline (folding carton, corrugated)
🔴 · springs / gears / cams generators 🔴 (kerf-partsgen-reachable) · piping
/ P&ID / plant design 🔴 · HVAC duct fabrication 🔴 · hydraulic / pneumatic
manifold 🔴.

**Electronics:** IC / VLSI layout 🔴 · power one-line / switchgear 🔴 ·
lighting / photometric 🔴 (cable/harness 3D tracked at P1-7).

**Architecture:** structural RC / steel + rebar 🔴 · interior /
space-planning / FF&E 🔴 · kitchen / bath / cabinetry / millwork 🔴 ·
landscape 🔴 · fire-protection / sprinkler 🔴 · scaffolding / formwork 🔴 ·
energy / daylight / acoustic 🔴.

**Civil / infrastructure (distinct engines, named):** geospatial CRS engine
🔴 · TIN terrain + contours + cut/fill 🔴 · horizontal/vertical alignment +
corridor solver 🔴 · hydraulics / stormwater 🔴 · grading / earthwork 🔴 ·
plan-and-profile sheet engine 🔴 · LandXML + IFC-4.3-infra I/O 🔴 ·
bridge/tunnel 🔴 · water/wastewater 🔴 · geotechnical 🔴 · mining 🔴 ·
marine/dredging 🔴 · rail signaling 🔴.

**Vehicles:** aerospace + composites ply/layup 🔴 · marine / naval-architecture
hull fairing 🔴 (close to Kerf's NURBS strength — relatively reachable) ·
rail rolling stock 🔴. (Automotive itself tracked at P1-6/P1-7/P2.)

**Body-worn / medical / craft:** watchmaking / horology 🔴
(partsgen-reachable) · eyewear / frames 🔴 · footwear / last design 🔴 ·
dental CAD (crowns / aligners) 🔴 · orthopedic / prosthetics / implants 🔴 ·
hearing aids 🔴. (Jewelry tracked at P1-2.)

**Soft goods (distinct 2D/developable engine):** apparel / pattern-making +
drape 🔴 · technical textiles / sails / membrane / tensile 🔴 · upholstery /
leather 🔴.

**Fabrication:** laser / waterjet / plasma + nesting 🔴 · woodworking /
furniture / joinery + cutlist 🔴 · robotics cell / kinematics 🔴. (Sheet
metal is P0-3; lattice/DfAM is P2; 3-print slicing + 3/5-axis CAM shipped.)

**Scientific / niche:** optical / lens / ray-trace 🔴 · microfluidics / MEMS
🔴 · wind-turbine / large-energy structures 🔴 · theatrical / stage / rigging
🔴 · signage / large-format 🔴.

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
| **Implicit / function-rep (F-rep / SDF) modeling** | nTopology, ImplicitCAD | Field-driven lattices / TPMS / gradient materials. Geometry expressed as a math function is the *ideal* LLM substrate — no topology bookkeeping, infinitely composable, verifiable by sampling the field. Verified absent (no SDF/implicit/TPMS module). | 🔴 not started |
| **Generative / topology / multi-objective optimization (production-grade)** | Fusion Generative, nTop, OptiStruct | Manufacturing-constrained, multi-load-case, multi-objective, lattice-infill optimization. The LLM frames the objective + constraints in text and reads back a verified result. Verified: basic single-objective SIMP topo-opt shipped (`packages/kerf-topo`, FEniCSx); manufacturing constraints / multi-load / multi-objective / lattice-infill **not** — the deep, production-grade version is unbuilt. | 🚧 in flight |
| **Simulation pillar** *(user priority — emphasized)* | Abaqus, LS-DYNA, nCode, OpenFOAM / Ansys, Adams | Nonlinear FEA, explicit dynamics / crash, fatigue & durability, CFD, low/high-frequency EM, acoustics, multibody dynamics, coupled multiphysics. Physics is governing equations + boundary conditions = text; the LLM sets up the study and self-checks results. **Verified split:** `packages/kerf-fem` analysis enum was `linear_static \| modal \| thermal` (+ bonded contact) — that slice ✅ shipped, and a **reference-value suite** with citable Roark / Blevins / Incropera oracles (`pressure_load.py` + 43-test `test_fem_refvalues.py`, 42 green, one ASTM E1049 rainflow test skipped — `fatigue_fem._rainflow` bug flagged) landed this session. A **parallel FEM-hardening stream** is still in flight to match CalculiX / Z88 / Mystran depth (T-100); seed modules for `nonlinear`, `explicit`, `acoustics_fem`, `em_field`, `em_highfreq`, and `fatigue_fem` are present in `packages/kerf-fem/src/kerf_fem/` but not yet wired through the public analysis enum. **CFD foundation** also landed this session — `cfd_potential.py` (potential flow, `Cp(θ)=1−4sin²θ` analytic oracle) + `cfd_navier_stokes.py` (lid-driven cavity, Ghia Re=100 reference), 61 hermetic tests in `test_cfd.py`, **2-D laminar scope**; full CfdOF-class depth (turbulence k-ε / k-ω SST, 3-D unstructured meshing, OpenFOAM bridge) tracked at T-101. **Crash / multibody / coupled multiphysics still 🔴 not started.** | 🚧 in flight |
| **1D system simulation** | Modelica, Amesim, Simulink | Lumped-parameter thermal / hydraulic / electrical / control networks. Modelica is *text* — a declarative equation-based language — making this exceptionally AI-native. Verified absent. | 🔴 not started |
| **Manufacturing process simulation** | Moldflow, MAGMASOFT, AutoForm, Vericut | Mold-flow, casting solidification, stamping / forming, AM residual stress, machining (toolpath) verification, weld distortion. Closes the loop between design intent and a producible part the LLM can reason about. Verified absent. | 🔴 not started |
| **Automatic Feature Recognition (AFR)** | (re-parameterize imported "dumb" STEP into editable features) | Critical AI enabler: turns any imported boundary-rep solid into an editable parametric feature tree, so the LLM can edit *any* model — not just ones authored in Kerf. Verified absent (no feature-recognition module). | 🔴 not started |
| **Knowledge-based engineering / design automation / code-compliance** | KBE, DriveWorks | Engineering rules + standards checks (Eurocode / AISC / ACI / ASME / ISO) driven directly by the model. Rules and standards are *text* — extremely AI-native and a large differentiator. Verified absent as a general capability (only narrow PCB-DRC + railing checks exist). | 🔴 not started |
| **3D tolerance / variation analysis** | 3DCS, CETOL | Statistical stack-up + contributor analysis in 3D. Verified: 1D worst-case / RSS / Monte-Carlo stack-up shipped (`packages/kerf-mates` `tolerance.py`); **3D variation analysis 🔴 not started.** | 🚧 in flight |
| **PLM depth** | (product configurator, 150% / effectivity BOM, where-used, ECR / ECO, digital thread, MBSE / SysML traceability) | The digital thread is structured data + relationships = ideal for an LLM to traverse and keep coherent. Verified: file revisions + cloud git + configurations / variants + BOM rollup shipped (partial PLM); deep PLM (configurator, 150% / effectivity BOM, where-used, ECR/ECO, MBSE/SysML trace) **🔴 not started.** | 🚧 in flight |
| **Multi-CAD interop & geometry healing** | STEP AP242 / JT / Parasolid / QIF + automatic repair | Robust import/heal is what lets the LLM operate on the real-world ecosystem, not a walled garden. Verified: STEP I/O shipped; **AP242 / JT / Parasolid / QIF + automatic geometry healing 🔴 not started** (only internal ShapeFix passes inside surface booleans, not a general heal tool). | 🚧 in flight |
| **Reverse-engineering pipeline** | Geomagic, PolyWorks | Point cloud → segmentation → feature fit → parametric solid. Verified absent as a pipeline; quad-remesh (`packages/kerf-cad-core` `quad_remesh.py`) is an adjacent, reusable building block. | 🔴 not started |
| **Mechanism synthesis & motion** | MotionGen, Adams | Linkage / cam / gear-train *synthesis* + kinematics. Synthesis is an inverse problem stated in text (motion spec → mechanism) — very AI-native. Verified: mates constraint solver shipped (`packages/kerf-mates` `solver.py`); **mechanism synthesis 🔴 not started.** | 🚧 in flight |
| **Sustainability / LCA** | One Click LCA | Embodied-carbon / circularity computed straight from the model + a materials database. Data-native, increasingly *mandated* by regulation. Verified absent. | 🔴 not started |
| **Robotics / offline programming** | RoboDK, Process Simulate | Robot-cell simulation + path generation. Toolpaths and robot programs are text — naturally AI-native. Verified absent; 5-axis CAM (`packages/kerf-cam` `five_axis/`) is an adjacent, reusable path-gen base. | 🔴 not started |
| **Nesting / cut & material optimization** | (sheet / textile / wood / stone nesting) | Cross-cutting, high-leverage packing/optimization shared by laser/waterjet/plasma, woodworking, apparel, and stone — one solver serves many sectors. Verified absent. | 🔴 not started |

---

## §4 — Shipped ledger (condensed)

One line per shipped capability. Detail lives in the linked plan/doc — the
roadmap no longer narrates it.

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
| **Composites engineering** | Fibersim, CATIA Composites | Ply-book / laminate / draping / fiber-steering. Spans aerospace, automotive, wind, and marine — high value, but a specialized layup engine. | 🔴 not started |
| **Medical / patient-specific** | Materialise Mimics / 3-matic | DICOM → surgical guides / orthotics / implants. High societal value and fast-growing; needs a medical-imaging-to-geometry pipeline. | 🔴 not started |
| **Process plant & pressure vessels** | AVEVA E3D, PV Elite, ISOGEN | Spec-driven piping / isometrics + ASME BPVC / PD5500 vessels. Huge industrial footprint; rule-native (good long-term AI-fit). | 🔴 not started |
| **Optical / photonics** | Zemax, PIC tools | Lens design + integrated optics. Math / parametric substrate → very AI-native long-term once the physics solvers exist. | 🔴 not started |

*Cross-reference (not duplicated here): civil sub-engines and marine /
naval-architecture hull fairing are already seeded at **P3 (§3)** because they
are nearer-term reachable; they are tracked there, not in this horizon table.*

---

## How to contribute

Pick a task from [`tasks.md`](./tasks.md) (sized for a single isolated agent
run), or open an issue proposing a new P3 sector line. The roadmap states
*why* and *in what order*; `tasks.md` is the *how*. Keep them in sync: when a
priority moves here, move the corresponding tasks there.
