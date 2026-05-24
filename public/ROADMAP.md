# Kerf — Roadmap

**Status glyphs:** `✅ shipped` · `🚧 in flight` · `🔴 not started`

---

## North Star

**The most comprehensive CAD on Earth — a single tool in which a person can design *anything*.** Mechanical engineering, electronics, PCB, architecture, civil engineering, drafting, jewelry, automotive — and every other CAD sector, including the small and niche ones. We are doing **everything**. Nothing here is "cut." Lower priority means *later*, not *dropped*.

This is a **priority-ordered** roadmap, not a date-ordered or effort-ordered one. The tiers (P0 → P3) express sequence and leverage: which items earn the most credibility per unit of work.

Kerf is dual-licensed: the OSS core (MIT) and the hosted-tier code under `packages/kerf-{billing,cloud}/` + `src/cloud/`.

### Why chat-driven CAD works

Kerf is **chat-driven** CAD. Every capability is designed around one constraint:

> *Can the LLM produce and re-edit this deliverable through a text-native tool, and verify the result?*

Professional CAD is overcomplicated mostly because of command-discovery affordances (ribbons, palettes, wizards) that an LLM does not need. Kerf ships professional **capability** while deliberately not shipping professional **UI complexity**. This makes the roadmap shorter than it looks: many "pro features" are UX wrappers around a parametric core we expose as a text schema + LLM tool + verifier.

**Hard guardrail:** simplification is about *authoring mechanics only*. It is never an excuse to drop a domain or to skimp on correctness, output formats, or standards compliance. Those are *more* important under an LLM, not less.

---

## Platform foundation

The sector work only matters if you **own your work, are not locked in, and can run Kerf wherever you want**. Four commitments, all decided:

1. **Every cloud project is a real git repository** — `git clone`-able with stock git, no special client. Large or binary files are auto-detected and stored with a small in-git pointer. Version control is two complementary layers: fine-grained automatic file history *and* deliberate, shareable commits with GitHub sync.

2. **One client, cloud by default, easy optional self-host** — `pip install kerf` for the hosted cloud; `pip install 'kerf[server]'` + bring-your-own-Postgres + `kerf serve` for self-host. Same client, same data model, both paths first-class.

3. **Portability is the anti-lock-in guarantee** — `kerf sync` mirrors to a local folder with two-way sync; `kerf export` / `kerf import` produce and ingest a plain file tree. Moving a project between cloud and self-host is painless.

4. **A fully-local / offline desktop app is committed but demand-gated** — portability + two-way sync + easy self-host is the complete launch answer to "I want to own my data." The standalone offline desktop build is sequenced behind real demand.

---

## What shipped

### Latest delta — 2026-05-24

**Structural code design** ✅ — AISC 360-22 (Ch. E/F/H members + connections + base-plate, LRFD+ASD); ACI 318-19 (flexure/shear/PM + punching §22.6 + torsion §22.7); NDS 2018 timber; ASCE 7-22 load combos + ELF + RSA/Newmark seismic. Full Eurocode: EC2, EC3, EC5, EC8.

**Native FE** ✅ — MITC4 plate/shell (Bathe-Dvorkin) + modal via inverse iteration; 2D/3D frame stiffness + story drift; multi-axial critical-plane fatigue (Findley, SWT-3D, Brown-Miller); geotech liquefaction triggering (Seed-Idriss/Tokimatsu).

**Machine elements depth** ✅ — ISO 6336 gear rating Method B; ISO/TS 16281 bearing modified life (aISO); planetary gearbox (3 Willis modes + compound); Taylor extended tool-life + Gilbert economics.

**Thermo-fluid depth** ✅ — IAPWS-IF97 steam Regions 1/2/4; Bell-Delaware shell-and-tube HX (TEMA + 5 correction factors); transient pipe-network (MOC waterhammer + surge-tank); ASHRAE CLTD/RTS transient cooling loads.

**Electronics / power depth** ✅ — IBIS-AMI signal integrity (Bergeron + PRBS eye); AC PDN impedance + decap optimiser; Newton-Raphson AC load-flow; IEC 60255 + IEEE C37.112 protection coordination + IEEE 1584-2018 arc-flash; fibre-optic link budget.

**Aero / marine / space depth** ✅ — 3D VLM + viscous strip drag + Prandtl-Glauert/Kármán-Tsien + Korn-Lock wave-drag; strip-theory seakeeping RAOs (Lewis-form + JONSWAP); Holtrop-Mennen resistance + EHP; multi-revolution Lambert (Lancaster-Blanchard/Izzo 2015).

**Manufacturing depth** ✅ — adaptive/trochoidal CAM HSM + rest machining; moldflow Hele-Shaw front tracking + weld-line + air-trap; casting Chvorinov + riser sizing + gating; NFP true-shape polygon nesting (57.6 % L-shape utilisation).

**Verticals** ✅ — dental anatomic crown (multi-cusp fan, not placeholder); Swiss lever escapement + mainspring + balance-wheel; solar PV partial shading + bypass-diode + MPPT; analog PVT corner simulation (60 corners + Monte-Carlo mismatch).

**Tolerancing / QA** ✅ — 3D vector-loop tolerance stackup (6-DOF Jacobian); SPC control charts (Shewhart/CUSUM/EWMA + Nelson/WECO); ISO 286 limits & fits.

**Optics / acoustics** ✅ — Gaussian beam (complex-q + ABCD + M² + fibre coupling); non-sequential ray tracing + ghost detection; wave-domain room acoustics (image-source IR + Schroeder RT60 + SEA); Seidel S5 corrected.

**Implicit geometry** ✅ — F-rep CSG (union/intersect/subtract/blend/shell) + domain warps (twist/taper/wave) in `kerf_cad_core.frep.csg`.

**Materials + LCA** ✅ — Ashby database to ~200 materials (14 families) with Pareto-frontier multi-objective selection; full ISO 14040/44 LCA (4 phases, 6 impact categories, Monte-Carlo uncertainty).

**Compare matrices** ✅ — feature-matrix YAML for 14 reference CADs: Fusion 360, SolidWorks, Onshape, FreeCAD, Rhino, KiCad, CATIA, Creo, NX, Inventor, AutoCAD, Altium, Revit, Blender — 741 grounded rows total.

**Security hardening** ✅ — `/run-topo` auth gate; NFP `grid_step` clamped; PVT `n_mc` clamped; Yosys module-name injection blocked; shared `_guard_*` helpers extracted across 68 files (−2009/+129 lines net).

### Core platform

- **Auth + projects + files + chat (CRUD)** ✅ — Postgres, JWT, Google OAuth.
- **Plugin monorepo (`packages/kerf-*`)** ✅ — `kerf-core` app factory + entry-point loader; ~25 plugin packages; 864+ tests.
- **Single-binary build + brew/curl install** ✅ — embedded Vite SPA (~32 MB).
- **Auth-optional local mode** ✅ — `POST /auth/bootstrap-local` singleton user.
- **Cloud: workshop sharing, billing, LLM pricing, free/paid buckets + wallet** ✅ — USD-display, credits at cost, BYO-key plumbing.
- **Cloud: git (commits/branches/merge/GitHub sync) + git Storer** ✅.
- **Large-file git handling** ✅ — pointer kind, Phase 1.
- **Diff-based + compressed revisions** ✅ — 82× shrink.
- **Workspaces (orgs), activity timeline, avatars/CDN, collapsible chat** ✅.
- **E2E Playwright + per-plugin pytest suites** ✅.
- **Billing-ledger schema on fresh databases** ✅.

### Scripting / SDK

- **`.script.py` via `kerf-sdk`** ✅ — `/v1/rpc` JSON-RPC over the LLM tool registry; API tokens; PyPI publish.
- **SDKs: Python · TypeScript · Rust · Go · Lua** ✅ — same `/v1/rpc` wire format.

### Parametric core

- **Equations / global parameters** ✅ — `.equations`, mathjs.
- **Configurations / variants** ✅ — per-file param overrides, BOM rollup.
- **Materials database** ✅ — `.material` kind, 200 seeded materials.
- **Two coexisting kernels** ✅ — `.jscad` (mesh) + `.feature` (OCCT BRep), shared `.sketch`/`.assembly`/`.drawing`.
- **Pure-Python B-rep + NURBS kernel** ✅ — validated `Body` topology, tolerant booleans, G1/G2 fillets, closest-point, hardened SSI, parametric history DAG with persistent face naming. 620 hermetic analytic-oracle-asserted tests.

### Geometry kernel — depth

The pure-Python kernel (`packages/kerf-cad-core/src/kerf_cad_core/geom/`) now matches Rhino/Blender-class construction depth with an analytic foundation:

| Module | Description | Status |
|---|---|---|
| **`brep.py`** | B-rep topology: radial-edge `Body→Solid→Shell→Face→Loop→Coedge→Edge→Vertex`, nine Euler operators, Euler–Poincaré invariant enforced | ✅ shipped |
| **`brep_build.py`** | Analytic verbs (box/cylinder/sphere/Coons patch) → `validate_body`-clean `Body` | ✅ shipped |
| **`boolean.py`** | Tolerant pure-Python solid booleans (regularised cut/fuse/common) over the primitive matrix, 2-manifold result | ✅ shipped |
| **`fillet_solid.py` / `chamfer.py`** | G1/G2 surface blend + edge fillet + variable chamfer | ✅ shipped |
| **`offset.py`** | Exact-distance surface/curve/loop offsets with self-intersection trim | ✅ shipped |
| **`coons.py`** | Boundary-interpolation Coons patches, exact to 1e-12 | ✅ shipped |
| **`inversion.py`** | Closest-point / point-inversion (Piegl 6.1, analytic partials on rational surfaces) | ✅ shipped |
| **`intersection.py`** | Hardened SSI: loop-detection, tangential-branch detection, small-loop guard, analytic specialisations | ✅ shipped |
| **`geom/history/`** | Parametric history DAG + `feature_id::role::fingerprint` persistent naming — downstream fillet survives upstream parameter edits | ✅ shipped |
| **G3 surfacing** | `surface_blend_g3` / `blend_srf_g3`, curvature-rate continuity oracle, zebra/reflection-line analyser, class-A acceptance harness — all verified, **wiring in progress** (GK-P series) | 🚧 in flight |
| **General solid boolean** | NURBS-faced / non-axis-aligned solids (today: axis-aligned only; general CSG delegates to OCCT worker) | 🔴 not started |

**GK-P (parity) series in flight.** A four-agent survey of Kerf vs ~18 kernel-relevant CADs found a concrete, finite gap list. GK-01..GK-139 are landed. The `GK-P` series (tracked in `tasks.md`) closes the remaining gaps:

- **Wiring** — expose shipped class-A math (G3 blends, zebra analyser, curvature-rate oracle) from `geom/__init__.py` and `surfacing.py`; all small, first in queue.
- **Foundational kernel** — general solid boolean for NURBS-faced bodies, MatchSrf G3, isophote/EMap, Stam limit-tangents + G1 at extraordinary SubD points, fractional creases, analytic surface derivatives.
- **Construction verbs** — loft guide-rails, sheet-metal hem/jog/multi-flange, direct-edit non-planar + delete-face, weldment gussets/end-treatments, surface patch-from-points.
- **SubD / mesh** — multires displacement, SDF CSG + marching-cubes, sculpt brush engine, isotropic remesh, surface-snap retopo, LSCM UV unwrap.
- **Architectural geometry** — B-rep→2D tessellate, roof/curtain-wall/corridor generators, wall compound-layer offset, hatch/section-fill.
- **Sketcher** — collinear constraint, ellipse solver entity, G2 continuity.
- **Interop** — 3DM write with read→write→read Hausdorff oracle.

### Mechanical / CAD

- **OCCT `.feature` Phase 2/3** ✅ — Pad/Pocket/Revolve/Hole/Fillet/Chamfer/Shell/Sweep/Loft/Push-Pull/Linear-Polar-Mirror patterns; face/edge gumball.
- **2D sketcher v1 + v2** ✅ — full constraint set, trim/extend, ellipse, B-spline, bezier, fillet, mirror, patterns.
- **Assembly model + 3D mates** ✅ — coincident/concentric/parallel/perp/distance/angle/tangent; gradient-descent solver.
- **Tolerance stack-up** ✅ — worst-case/RSS/Monte-Carlo + auto chain-walk.
- **2D drawings** ✅ — multi-sheet, dimensions, GD&T frames, section hatching, leaders/balloons, centerlines.
- **NURBS surfacing (Phase 4)** ✅ — sweep1/2/network/blend/loft + `surface_continuity` (C0–C2/G0–G2); surface-direct boolean; trim-by-curve; curvature-comb viz; zebra/reflection-line viewport toggle. G3 *enforcement* on the OCCT side is structurally impossible (absent from OCCT's type system); pure-Python is the G3 path.
- **Rhino parity** ✅ — 3DM I/O, SubD (Catmull-Clark), quad remesh, mesh tools, layers/display, parametric `.graph`, render output.
- **Persistent face naming** ✅ — sketch-anchored + topo-hash (frontend T1–T7) plus kernel-side `feature_id::role::fingerprint` selector in the pure-Python DAG.

### Simulation / manufacturing

- **FEM** ✅ — FEniCSx + CalculiX: linear-static + modal + steady thermal + bonded contact; reference-value suite with Roark/Blevins/Incropera oracles (42 of 43 green).
- **CFD foundation** ✅ — 2-D laminar: potential flow (`Cp(θ)=1−4sin²θ` oracle) + lid-driven cavity (Ghia Re=100 reference); 61 hermetic tests.
- **Topology optimization** ✅ — SIMP via FEniCSx; NURBS surface fit; multi-body.
- **CAM** ✅ — 2.5D + 3D parallel/waterline + lathe + 5-axis constant-tilt + 3+2 indexed; tool DB; LinuxCNC/GRBL/Fanuc posts.
- **Slicing** ✅ — plane-section, CNC layered, 3D-print G-code (Cura, Tier 1).

### Electronics

- **KiCad-class PCB design** ✅ — ERC, hier-schematic, buses/diff-pairs, net classes/rules, length tuning, via stitching/teardrops, shove router, copper pour, DRC.
- **Fabrication package** ✅ — Gerber RS-274X, Excellon drill, IPC-2581, ODB++, pick-and-place, fab BOM, 3D board STEP export.
- **SPICE + RF + autorouting** ✅ — ngspice, scikit-rf S-params/Smith chart, FreeRouting DSN/SES.
- **Wiring/harness** ✅ — WireViz YAML→SVG (2D; 3D in flight at P1-7).
- **PLC** ✅ — MATIEC lint Tier 1.
- **Silicon / IC layout** ✅ — VHDL + Verilog parsers; GHDL + Yosys + ngspice bridges; GDS II / OASIS I/O; SKY130 PDK; LEF/Liberty readers; OpenROAD place-and-route; DRC + LVS + parasitic extraction; mask fracturing. T-231..T-248.
- **Firmware / embedded** ✅ — board catalogue (Arduino/ESP32/STM32/RP2040/AVR); library cache; direct-gcc orchestrator (`avr-gcc`/`arm-none-eabi-gcc`/`xtensa-esp32-elf`); upload wrappers; serial monitor panel; LLM tools. T-225..T-230.

### Architecture / BIM

- **`.bim` text-DSL → IFC4** ✅ — walls/slabs/spaces/openings/levels/site.
- **IFC import Tier 1 + 2** ✅ — walls/slabs/spaces/levels/sites + openings/MEP/families/schedules.
- **Revit parity** ✅ — `.family`/`.schedule`/`.view`/`.sheet`, categories, type-vs-instance, phasing/filters, stairs/railings, MEP, curtain wall.

### Aerospace / composites

- **Applied aerodynamics** ✅ — ISA atmosphere, VLM/thin-airfoil, flight mechanics, propulsion, Breguet range/endurance; 6-DOF; orbital mechanics (Kepler/Lambert/Hohmann); rocket propulsion (CEA-lite); ADCS (quaternion + reaction wheels + magnetorquers); spacecraft thermal network.
- **Composites (CLT)** ✅ — ABD matrix, per-ply stress/strain, Tsai-Wu/max-stress/Hashin failure indices, first-ply-failure, laminate moduli.
- **Aeroelasticity** ✅ — flutter boundary (Theodorsen + p-k method), doublet-lattice.

### Library / parts / BOM

- **Library system v1 + BOM** ✅ — `kind='part'`, distributor APIs (DigiKey/Mouser/LCSC), curated manufacturer libs.
- **Cross-project parts** ✅ — external_ref, lockfile, derived-artifact cache.
- **kerf-partsgen** ✅ — 5 ISO/DIN family generators shipped.

### Frontend / UX

- **Viewport** ✅ — Render dropdown, Daylight mode, Exposure slider, PCF soft-shadows, quality presets (Low/Medium/High/Ultra), material editor panel (roughness/metalness/opacity/emissive), viewport keybindings.
- **GDS layout viewer** ✅ — layer palette, zoom/pan, net highlight, DRC overlay.
- **Monaco editor modes** ✅ — VHDL, Verilog, SPICE syntax highlighting.
- **Compare pages** ✅ — 14 head-to-head comparison routes.
- **Docs viewer redesign** ✅ — grouped sidebar, breadcrumbs, TOC, audit-filter.
- **Pre-React boot loader** ✅ — Kerf-branded SVG triangles loader, zero flash.
- **Touch + responsive polish** ✅ — Renderer + Gumball touch gestures, Editor responsive layout.
- **Render output** ✅ — PBR hero / share-card pipeline at 2048×2048; Blender Cycles offline path for jewelry.

---

## In flight

| # | What | Why it matters | Status |
|---|---|---|---|
| **P0-5** | **Large-assembly performance ceiling** — measured budget + LOD / lazy-load for 1000s of parts. Automotive full-vehicle DMU is the extreme case. | First credibility block for automotive and large mechanical. | 🔴 not started |
| **P0-6** | **Broaden text / code file support** — common text and code files open as editable text with syntax highlighting. | Every project benefits; gates firmware depth. | 🔴 not started |
| **P0-7** | **Project export / materialize foundation** — plain file-tree for `kerf export` / `kerf import` / `kerf sync`. | The anti-lock-in guarantee's substrate. | 🔴 not started |
| **P0-8** | **Testing / seeding / deploy-hardening** — broad test suites + realistic seed data + one-command local/dev loops. | Quality gate before broader build-out. | 🚧 in flight |
| **P1-7** | **3D in-vehicle wiring harness** — route through DMU, bundle/segment/connector libs, formboard flatten, length/gauge/voltage-drop. | Closes the ECAD-to-harness loop. | 🔴 not started |
| **P1-8** | **Git-as-substrate with automatic large-file handling + free forks** — every project a stock-`git clone`-able repo; large/binary files auto-detected + kept in storage with a small in-git pointer; near-instant forks via shared content-addressed storage. | Own-your-data guarantee. | 🚧 in flight |
| **P1-9** | **Unified `pip install kerf` client** — cloud-default, easy optional self-host; fail-fast on missing database URL. | Reach: one client for all install modes. | 🚧 in flight |
| **P1-10** | **Local folder sync + export/import portability** — `kerf sync` two-way folder mirror; `kerf export` / `kerf import` plain file tree; symmetric cloud ↔ self-host. | Anti-lock-in, demonstrable not just promised. | 🔴 not started |
| **GK-P** | **Geometry kernel parity series** — close the gap list from the multi-CAD survey (GK-01..GK-139 landed; wiring + foundational + SubD + architectural geometry remaining). | Every persona's work quality depends on kernel robustness. | 🚧 in flight |
| **T-100** | **FEM matching CalculiX / Z88 / Mystran depth** — nonlinear, explicit, acoustics, EM, fatigue beyond the verified linear-static+modal+thermal slice. | Serious simulation work. | 🚧 in flight |
| **T-101** | **CFD (CfdOF-class)** — turbulence models, 3-D unstructured meshing, OpenFOAM bridge beyond the 2-D laminar foundation. | Fluid and aero simulation. | 🚧 in flight |
| **Hosted infra migration** | **Cloud infrastructure migration** — GPU compute instances needed for Cycles renders and future GPU workloads. Migration in progress; no self-host impact. | GPU render price drops 2-3× when complete. | 🚧 in flight |

---

## Planned next

### Depth gaps (concrete, near-term)

| # | Gap | vs | Status |
|---|---|---|---|
| G-3 | **Interactive push-and-shove diff-pair tuning** — Kerf has length tuning only | KiCad / Altium | 🔴 not started |
| G-4 | **Broader ECAD import** — Allegro / PADS / gEDA / Eagle v10 | Altium / Cadence | 🔴 not started |
| G-5 | **Kernel G3 / class-A leading** — wired G3 blends + curvature-comb + imprint | Alias / ICEM Surf | 🚧 in flight |
| G-6 | **SubD authoring with creases + edit workflow** | Rhino 8 SubD | 🔴 not started |
| G-7 | **Render: caustics + dispersion** — in-browser path-tracer + Blender Cycles spectral | Cycles / V-Ray / KeyShot | 🔴 not started |
| G-8 | **Direct + parametric history coexistence** | Fusion / Inventor / Onshape | 🔴 not started |
| G-9 | **Full joint system** — rigid/revolute/slider/cam/gear/pin-slot | Inventor / SolidWorks | 🔴 not started |
| G-10 | **BIM parametric family authoring UX** | Revit | 🔴 not started |
| G-11 | **BIM family library** — curated catalog | Revit | 🔴 not started |
| G-12 | **BIM walls / doors / windows / slabs full parametric** | Revit | 🔴 not started |
| G-13 | **BIM stairs / ramps full** | Revit | 🔴 not started |
| G-14 | **BIM structural grid + framing** | Revit Structure / Tekla | 🔴 not started |
| G-15 | **BIM site / earthwork (toposolids)** | Revit / Civil 3D | 🔴 not started |
| G-16 | **BIM material catalogue with render appearance** | Revit / Enscape | 🔴 not started |

### Long-tail verticals

Everything committed, lowest priority. Ordered roughly by near-term readiness.

**Mechanical / product:** cams generators · woodworking / furniture / joinery + cutlist · power one-line / switchgear · lighting / photometric · interior / space-planning / FF&E · kitchen / bath / cabinetry / millwork · landscape · scaffolding / formwork.

**Vehicles:** composites ply/layup authoring (draping / fiber-steering / Fibersim class) · hull fairing (NURBS-reachable) · 3D harness routing.

**Civil / infrastructure (distinct engines):** plan-and-profile sheet engine · LandXML + IFC-4.3-infra I/O · bridge/tunnel · water/wastewater · mining · marine/dredging · rail signaling. *(CRS engine, horizontal/vertical alignment, hydraulics, earthworks, geotechnical already shipped.)*

**Body-worn / medical / craft:** watchmaking / horology · eyewear / frames · footwear / last design · dental CAD (crowns/aligners) · orthopedic / prosthetics · hearing aids.

**Soft goods (distinct 2D/developable engine):** apparel / pattern-making + drape · technical textiles / sails / membrane / tensile · upholstery / leather.

**Scientific / niche:** microfluidics / MEMS · signage / large-format.

**Silicon next:** verification depth + post-silicon (cocotb testbench harness, power analysis, STA, clock-tree synthesis, formal equivalence, Tiny Tapeout / Efabless harnesses). T-249..T-258.

**Firmware next:** RTOS primitives, OTA, RTOS-aware debugger, power profiling, pin-map cross-check vs PCB, USB-class drivers. T-259..T-265.

**Aerospace next:** XFOIL-class viscous solver, aircraft conceptual sizing (Raymer/Roskam), stability derivatives, aero-acoustics (FW-H), heat-shield/ablation, aerospace fasteners. T-266..T-272.

**Platform (demand-gated post-launch):** fully-local / offline / no-account desktop app — committed but not a launch pillar. Portability + two-way sync + easy self-host is the launch answer.

### Strategic AI-native capabilities

These are roadmap-level moats that span every sector simultaneously and compound leverage instead of adding it linearly.

| Capability | Status |
|---|---|
| **Generative / topology / multi-objective optimization** — manufacturing-constrained, multi-load-case, lattice-infill. Basic single-objective SIMP shipped; production-grade unbuilt. | 🚧 in flight |
| **Simulation pillar** — nonlinear FEA, explicit dynamics / crash, fatigue & durability, CFD (full turbulence), low/high-frequency EM, acoustics FEM, coupled multiphysics. Linear-static + modal + steady thermal + CFD 2-D laminar shipped. | 🚧 in flight |
| **Automatic Feature Recognition (AFR)** — turns any imported "dumb" STEP into an editable parametric feature tree; critical for the LLM to edit any model, not just ones authored in Kerf. | 🔴 not started |
| **Knowledge-based engineering / code-compliance** — AISC/ACI/Eurocode/ASME/ISO rules driven directly by the model. Shipped: AISC 360-22 + ACI 318-19 + EC2/3/5/8 + NDS 2018 + ASCE 7-22 + ISO 6336 + IAPWS-IF97 + IEEE 1584 + IEC 60255. General KBE configurator layer unbuilt. | 🚧 in flight |
| **3D tolerance / variation analysis** — statistical stack-up + contributor analysis. Shipped: 1D worst-case/RSS/Monte-Carlo + 3D vector-loop 6-DOF Jacobian. Full FEA-coupled variation simulation ahead. | 🚧 in flight |
| **PLM depth** — configurator, 150% / effectivity BOM, where-used, ECR/ECO, digital thread, MBSE/SysML traceability. File revisions + cloud git + configurations + BOM rollup shipped (partial PLM). | 🚧 in flight |
| **Multi-CAD interop & geometry healing** — STEP AP242 / JT / Parasolid / QIF + automatic repair. STEP I/O shipped; general heal unbuilt. | 🚧 in flight |
| **Reverse-engineering pipeline** — point cloud → segmentation → feature fit → parametric solid. | 🔴 not started |
| **Mechanism synthesis & motion** — linkage / cam / gear-train *synthesis*. Constraint solver shipped; synthesis unbuilt. | 🔴 not started |

---

## Deliberately not building

This list is only AI-redundant *authoring/UX interaction paradigms* — not skipped domains or correctness features.

| Not building | Why |
|---|---|
| Visual node programming (Grasshopper / Dynamo / Sverchok) | The LLM writing a parametric script *is* the graph. `.script.py` + SDKs + JSCAD + `.graph` cover the value. |
| Ribbon / toolbar maximalism | The LLM is the command palette — discovery is a chat sentence, not a menu hunt. |
| Macro recorders / scripting-GUI builders | The LLM is the macro author; it writes `.script.py` directly. |
| Gumball / direct-modeling maximalism | Keep a basic gumball; the LLM edits the feature tree. |
| In-app wizards / tutorials / onboarding tours | The chat is the wizard — context-specific guidance on demand. |

---

## How to contribute

Pick a task from [`tasks.md`](./tasks.md) (sized for a single isolated agent run), or open an issue proposing a new long-tail sector line. The roadmap states *why* and *in what order*; `tasks.md` is the *how*. Keep them in sync: when a priority moves here, move the corresponding tasks there.
