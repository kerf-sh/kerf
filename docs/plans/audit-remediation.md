# Audit Remediation Roadmap

Origin: 2026-05-24 full-codebase audit (13 parallel agents) covering frontend
wiring, stubs, redundancy, and security. This roadmap breaks the findings into
discrete, dispatchable tasks executed by worktree-isolated Sonnet agents and
integrated by commit SHA.

Legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[!]` flagged / needs decision

Operating rules for the loop:
- One agent owns a disjoint file-set per wave (no two concurrent agents edit the same file).
- Each agent VERIFIES the finding against current code before fixing; reports false positives instead of forcing a change.
- Each agent runs the relevant tests and commits in its worktree; parent integrates by SHA.
- Never `DROP SCHEMA` / reset the shared Postgres DB while another agent runs.
- No backwards-compat shims; DBs are reset, baseline migrations are consolidated.

---

## Phase 1 — Security (highest priority)

- [ ] **P1-API** — kerf-api `routes.py`: (a) API-token revoke IDOR — add workspace/owner filter to `revoke_api_token`; (b) `delete_share_link` — verify `lid.project_id == pid`; (c) `accept_share` — fix `project_id` passed where `workspace_id` expected; (d) remove stale `p.owner_id` references in admin publisher SQL; (e) billing fail-closed — replace `except Exception: bucket=None` zero-cost fallthrough with hard 503; (f) `import_step` SSRF — block RFC1918/loopback/link-local after DNS resolve; (g) add `require_auth` to any kerf-api route missing it; (h) unify password hashing to bcrypt (drop SHA-256 path).
- [ ] **P1-SILICON** — kerf-silicon: sanitize `top`/`top_module` (`^[A-Za-z_]\w*$`) before Yosys script interpolation (`routes_silicon_synth.py`, `yosys_bridge.py`); add `require_auth` to `/silicon/synth`.
- [ ] **P1-IMPORTS** — kerf-imports: fix zip-slip in `kicad.py` + `kicad_library.py` (validate each member path stays within tmpdir; sanitize `file.filename`); add `require_auth` to `/import-kicad`, `/import-kicad-library`.
- [ ] **P1-RUNROUTES** — kerf-render + kerf-slicing + kerf-firmware: add `require_auth` to `/run-render`, `/run-print-slice`, `/firmware/*`; enforce workspace confinement on `stl_path` / `source_path` / `hex_path` (`resolve().is_relative_to(workspace_dir)`).
- [ ] **P1-HARDENING** — fail-closed secrets: refuse to boot in non-dev if `jwt_secret`/`password_pepper` (kerf-core `config.py`) or share-HMAC (kerf-cloud `share_link.py`) are the dev defaults; add SHA256 integrity check to freerouting JAR download (kerf-electronics).
- [ ] **P1-WEBXSS** — frontend: wire `markdownSanitize` (`urlTransform` + allowed elements) into `ChatPanel.jsx` and `CompareMd.jsx`; add a Content-Security-Policy (`index.html` meta or server header).

## Phase 2 — Frontend wiring + dead-code cleanup

- [ ] **P2-EDITOR** — `Editor.jsx`: wire the finished-but-orphaned viewers — CAMView (`.cam`), TopoView `onRun`→POST `/run-topo`, AirfoilPolarPlot (`.airfoil`), BIMView (IFC), OrbitViewer; plus create+mount the small composites CLT/failure panel.
- [ ] **P2-PLUGINREG** — register `routes_aero_orbit` in `plugin.py` (orphan router); audit for other unregistered routers.
- [ ] **P2-SIDEBAR** — new sidebar widgets for routes with real compute and no UI: atmosphere, tsiolkovsky/CEA (`aeroPropulsionBridge`), RF link budget (`/run-rf-study`), silicon synth viewer.
- [ ] **P2-DEADCODE** — delete stranded `KerfVs*.jsx` compare pages (4) + their routes in `App.jsx`; resolve `CompareLanding` vs `index.jsx` duplicate; remove `Settings.jsx`, `CommitDiff.jsx`, `cloud/DiffViewer.jsx`, `stores/dirtyStore.js`; refresh `docs/wiring-audit.md`.
- [ ] **P2-TODOCLUSTER** — resolve `TODO(parent): wire` components: MaterialPbrEditor→MaterialEditor, Chat AtopilePreview/CircuitJsonPreview→ChatMessage, LadderEditorWithFlow, AutosaveStatus; wire or delete the 9-panel render-settings cluster.

## Phase 3 — Stubs

- [ ] **P3-SURFACING** — `surfacing.py:~960` `sketch_to_nurbs_curve()` arc branch: implement arc→NURBS instead of silent `pass`/`None`.
- [ ] **P3-CEALITE** — `routes_aero_propulsion.py`: actually use `rocketcea` when importable instead of always falling through to the lookup table.
- [ ] **P3-RUNCAM** — kerf-cam `/run-cam`: return an honest `{status:"pending"}` (matching FEM/CFD convention) when opencamlib is absent, instead of mock 10×10 G-code.

## Phase 4 — Redundancy / shared-core extraction (preserve public APIs)

- [ ] **P4-FRICTION** — extract one Colebrook-White friction-factor util; refactor `piping/process.py`, `fluidpower/circuit.py`, `hvac/ducts.py`, `boiler/plant.py`, `kerf-hvac/pressure.py`.
- [ ] **P4-STEAM** — single steam-saturation property module (use boiler's complete set); `thermocycle` Rankine + `refrigeration` call through it.
- [ ] **P4-SOLAR** — shared solar-geometry (Spencer 1971); dedupe `solarpv/sizing.py` ↔ `kerf-energy/solar.py`.
- [ ] **P4-HYDRO** — single Simpson hydrostatics core (navalarch canonical); `marine/hull.py` + `kerf-marine` delegate.
- [ ] **P4-ITGRADE** — single ISO-286 IT-grade table in `gdt/`; `gdt_callouts` + `kerf-mates/tolerance.py` import it.
- [ ] **P4-LINALG** — shared pure-Python mat/vec/quat util; dedupe `mbd/solver.py`, `robotics/arm.py`, `kerf-motion`.
- [ ] **P4-CONCRETE** — `kerf-structural/rc_beam.py` imports `_beta1` + ACI flexure from `concrete/design.py`.
- [ ] **P4-WORMBEVEL** — `wormbevel/design.py:bevel_agma_stress` calls `gearstrength` AGMA functions.
- [ ] **P4-SCAN** — `scan/fit.py` delegates plane/sphere/cylinder RANSAC to `reverse_engineering/`.
- [ ] **P4-TPMS** — dedupe gyroid/schwarz-P between `geom/lattice.py` and `frep/sdf.py`.
- [ ] **P4-CUTPOWER** — single `cutting_power`; `cncfeeds` delegates to `cuttingtool` physics.
- [ ] **P4-GUARDS** — shared `_guard_positive`/`_guard_nonneg`/`_err` util; sweep callers (run LAST — touches many files).

## Phase 5 — Domain module merges (flagged: larger, API-affecting)

- [!] **P5-GEARS** — merge `gearbox`+`gearstrength`+`wormbevel` → `power_transmission/`.
- [!] **P5-LATERAL** — merge `seismic`+`windload` → `asce7_lateral/`.
- [!] **P5-LIFTING** — merge `crane`+`rigging` → `lifting/`.
- [!] **P5-MOTION** — fold `robotics/` FK/IK into `kerf-motion`.

These change the public module layout / LLM tool surface; attempt only after Phases 1–4 are green and verified, and re-confirm scope before executing.

---

## Phase 6 — Domain depth sweep (go as deep as possible, all domains)

Directive (2026-05-24): every engineering domain engine should reach **maximum
professional fidelity** — full coverage of governing standards/editions,
higher-order and validated methods, complete boundary/load/edge cases, and
regression tests against analytic or published references. Sequenced AFTER
Phases 1–4 so depth lands on consolidated/canonical code, not duplicates. Each
family's depth pass also absorbs the relevant Phase 5 merge. Per-family agent
brief: (1) enumerate the standards + methods a professional tool in this domain
has; (2) gap-analyse current code vs that; (3) implement the missing depth;
(4) add reference-validated tests; (5) wire new capability to LLM tools / routes.

- [ ] **D1-GEOMETRY** — geom, frep, surfacing/NURBS Phase 4, assembly, drawings, sketch solver, sheet-metal, thread, gdt rendering. Deepen: NURBS surfacing (loft/sweep/blend/fillet-surface), robust booleans, persistent face naming, full GD&T-on-drawing.
- [ ] **D2-STRUCTURAL** — beam, struct, fea, steelconn, concrete, timber, seismic, windload, fatigue, pressvessel, tank, firesafety (+kerf-structural, kerf-fem). Deepen: full AISC/ACI/NDS/Eurocode editions, plate/shell + nonlinear FE, modal/buckling, response-spectrum.
- [ ] **D3-MACHINE** — gears (gearbox+gearstrength+wormbevel merge), beltchain, clutchbrake, shaft, bearings, springs, fasteners, lubrication, cam, crane+rigging merge, conveyor, elevator. Deepen: full AGMA/ISO gear rating, bearing L10 + ISO/TS, fastener VDI 2230, EHL lubrication.
- [ ] **D4-THERMOFLUID** — thermocycle, refrigeration, boiler, heatxfer, heattreat, hvac, psychro, buildingenergy, combustion, fluidpower, pneumatics, pumpsys, piping, plumbing, flowmeter, waterhammer, vacuum, channel, spillway (+kerf-hvac/piping/cfd/microfluidics). Deepen: real refrigerant/steam property tables (CoolProp-grade), NTU-effectiveness HX, full ASHRAE loads, transient pipe networks.
- [ ] **D5-AEROSPACE-MARINE** — aero, turbo, combustion, windturbine, navalarch, marine, mooring, hydroturbine (+kerf-aero, kerf-marine). Deepen: full USSA76, VLM/panel + viscous coupling, 6-DOF + stability derivatives, orbital (multi-rev Lambert), full hydrostatics + stability + seakeeping.
- [ ] **D6-ELECTRONICS** — SI/EMC/PDN/PCB-thermal/antenna/battery/BMS/motordrive/gatedrive/leddriver, silicon (synth/STA/DRC/GDS), sysml1d. Deepen: full transmission-line + S-parameter SI, IBIS, PDN target-Z, STA with real liberty timing, P&R.
- [ ] **D7-MANUFACTURING** — cam (3/4/5-axis + posts), cncfeeds, cuttingtool, turning, gcode, casting, forming, injection, additive, welding, thermalcut, dfm, cmm, nesting (+kerf-cam/manufacturing/mold/slicing). Deepen: validated toolpath strategies, full feeds/speeds + tool-life, moldflow, DFM rule library.
- [ ] **D8-CIVIL-GEO** — civil, earthworks, pavement, railway, surveying, geodesy, geotech, hydrology, spillway (+kerf-civil, kerf-landscape). Deepen: full alignment/corridor, AASHTO pavement, bearing-capacity + settlement + slope methods, SCS/rational hydrology.
- [ ] **D9-DYNAMICS** — dynamics, mbd, kinematics, robotics (fold into kerf-motion), vibration, controls (+kerf-systems). Deepen: 3-D constrained multibody w/ contact, full FK/IK/Jacobian/dynamics, MDOF modal + FRF, state-space + modern control.
- [ ] **D10-ELECTRICAL-ENERGY** — elecpower, solarpv, harness (+kerf-energy, kerf-wiring, kerf-plc). Deepen: load-flow/short-circuit/protection coordination, full PV system + shading + inverter, harness electrical + routing.
- [ ] **D11-TOLERANCING-QA** — gdt, gdt_callouts, tolfits, tolstack, cmm, reliability (+kerf-gdnt, kerf-mates). Deepen: full ASME Y14.5 evaluation, 3-D tolerance stacks + Monte-Carlo, GR&R/SPC, FMEA/FMECA/MTBF.
- [ ] **D12-OPTICS-ACOUSTICS** — optics, photonics, acoustics. Deepen: sequential + non-sequential ray trace, aberrations, Gaussian beams, room/duct acoustics, transmission loss.
- [ ] **D13-VERTICALS** — jewelry, dental, horology, apparel, textiles, woodworking, interior, packaging, BIM/arch (+landscape). Deepen each vertical to its professional workflow depth.
- [ ] **D14-COST-MATERIALS** — costing, quoting, procsim, materials, matsel, ergonomics (+kerf-lca, kerf-rules, kerf-partsgen). Deepen: should-cost models, full material DB + Ashby selection, process-sim, LCA per ISO 14040.

Each Dnn is large and will span multiple agent waves; treat each as a mini-roadmap.

---

## Phase 7 — Scalability hardening

Directive (2026-05-24): audit + harden scalability (alongside the completed
redundancy + security audits). Populated from the scalability audit. Expected themes:
- [ ] **S7-JOBS** — move heavy/long compute (render, FEM, CFD, topo, slicing) off synchronous request handlers onto an async job queue with status polling; idempotency keys; backpressure; per-user concurrency caps.
- [ ] **S7-DB** — connection-pool sizing, N+1 query elimination, pagination on list endpoints, indexes for hot queries.
- [ ] **S7-STORAGE** — stream large artifacts (don't buffer in memory); signed/expiring URLs (ties to the security thumbnail finding).
- [ ] **S7-LIMITS** — rate limiting + request size limits + worker autoscale policy.

## Phase 8 — GPU compute backend (cloud Koyeb GPU + OSS-compatible)

Directive: add GPU instances on Koyeb for advanced rendering and advanced
projects (heavy FEM/CFD/topo), with an abstraction so OSS/self-host can use GPU too.
- [ ] **G8-IFACE** — define a `ComputeBackend` abstraction (enqueue job → run → artifact → notify) used by render + heavy-compute. Two implementations: `local` (host subprocess, optional local GPU via CUDA/Metal detection, CPU fallback) and `cloud-gpu` (Koyeb GPU service pool). MIT-root: the interface + local backend are open; the Koyeb-pool orchestration lives under the proprietary cloud/ tree.
- [ ] **G8-KOYEB** — Koyeb GPU service config (L4 default, scale-to-zero), on-demand spin-up per job, GPU worker image (Blender + CUDA), job dispatch + result fetch. Build kerf-workers GPU worker. **Do NOT `koyeb deploy` / provision GPU instances autonomously — user triggers deployment.**
- [ ] **G8-OSS** — self-host docs + config so a self-hoster points Kerf at a local/own GPU box; no proprietary dependency in the OSS path; graceful CPU fallback.
- [ ] **G8-WIRE** — route GPU-eligible jobs (render quality tiers, large sims) to the GPU backend; expose status in the UI (ties to TopoView/render wiring in Phase 2).

## Phase 9 — Billing for GPU + billing-model fix/run

Directive: fix and run the billing model to account for GPU.
- [ ] **B9-METER** — meter GPU-seconds as a billable resource; emit usage events from the GPU backend; atomic, server-authoritative credit decrement (builds on the P1-API billing fail-closed fix).
- [ ] **B9-BUCKETS** — extend the three-bucket model: GPU jobs require kerf_paid credits (priced at cost + markup, consistent with existing model); kerf_free = CPU-only or a tight GPU cap; kerf_byo / self-host = own infra, zero Kerf billing.
- [ ] **B9-MODEL** — update the `billingmodel/` calculator with GPU line items (Koyeb GPU service $/s + markup) and RUN it to produce refreshed pricing numbers; reconcile with the Free/Studio/Pro/Enterprise tiers.
- [ ] **B9-AUDIT** — close the billing-bypass + storage-URL-signing security findings as part of this pass.

Sequencing: Phase 7 (scalability) and the Phase 8/9 design depend on the
scalability + compute-architecture + billing-model audits (read-only, run first).

---

## Phase 6 execution — autonomous build/test loop (started 2026-05-24 ~05:00)

Mandate: run an ~8-hour self-paced loop driving `docs/domain_depth.md` toward
completion — surface engines in the UI, close depth gaps, remove redundancy,
fix security/correctness. Stop when the backlog is drained or 8 h elapse.

**Status going in:** Phases 1–4, 7, 8, 9 integrated. Audit + `domain_depth.md`
done. Remaining: the domain_depth Tier 1/2/3 backlog + GUARDS + sidebar.

**Operating rules:**
- ~5 Sonnet worktree agents at a time; integrate by SHA; refill on completion.
- Disjoint file-sets per wave (one owner for chokepoints: Editor.jsx, App.jsx, kerf-api routes.py, kerf-workers runner.py).
- Per-wave package tests must pass before integrate; periodic consolidated runs.
- Update `domain_depth.md` checkboxes + tasks in the same pass as each feature.
- Migrations folded into baseline (no ALTER shims). Never reset the shared DB.
- **No `koyeb deploy` / GPU provisioning; no `git push`.**
- UI cannot be visually QA'd here — UI features land with vitest + build green and are flagged for the user's visual sign-off (not claimed "perfect").

**Wave order:** Tier 1 (UI surfacing, highest ROI) + Tier 3 (correctness, cheap)
first, then Tier 2 (depth gaps), GUARDS alone last (touches many files).

**Completion criteria:** domain_depth Tier 1 fully wired; Tier 3 fixes done;
Tier 2 high-value items landed; GUARDS done; consolidated tests green; parity
snapshot refreshed. Anything beyond 8 h is reported as remaining long-tail.

