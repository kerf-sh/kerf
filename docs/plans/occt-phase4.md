# OCCT Phase 4 — T-104 decomposition (internal)

> **Internal planning doc.** `docs/plans/**` is excluded from the user
> docs viewer. This is the breakdown rationale for splitting the long-tail
> epic **T-104 "Kernel G3 + NURBS Phase 4 trim-by-curve + class-A
> leading"** into bounded single-Sonnet-agent sub-tasks **T-104a..h**,
> the same way the render epic was split into T-106a..f.
>
> Decomposed at HEAD `384f401`. Authoritative current-state sources read
> for grounding: `tasks.md` `### T-104` / `### T-106a..f`,
> `docs/plans/geometry-kernel-roadmap.md`,
> `docs/plans/nurbs-phase-4-full.md`, and the live kernel code under
> `packages/kerf-cad-core/src/kerf_cad_core/geom/` +
> `kerf_cad_core/surfacing.py`.

---

## 1. Why split it

T-104 as written is a single Tier-A P1 epic that bundles three
independently-shippable workstreams plus one structurally-impossible
ask:

1. **Trim-by-curve / imprint** — pure-Python face split by an SSI /
   projected curve (roadmap `GK-40`, plus a worker-side fallback).
2. **Class-A leading** — the surface-quality *workflow* (curvature
   combs + zebra + G-continuity acceptance gate; roadmap
   `GK-38`/`GK-64`).
3. **Algorithmic G3** — third-derivative-continuous blends. **This is
   the trap.** Stock OCCT *cannot* enforce G3: `GeomAbs_G3` does not
   exist in the `GeomAbs_Shape` enum (confirmed in
   `surfacing.py:1096-1100` and `nurbs-phase-4-full.md:5-6,41-42`).
   What *is* achievable is (a) a **pure-Python NURBS** G3 blend in
   `geom/blend_srf.py` (roadmap `GK-62`, no OCCT involved — pure math,
   so the impossibility does not apply to the Kerf pure-Python layer)
   and (b) the **already-shipped visualization** path (eyeball G3 via
   curvature combs). We must NOT write a sub-task that demands stock
   OCCT enforce G3 — that is the structurally-impossible item to flag.

Each of these is a different file-set, a different oracle, and a
different risk profile. Bundled, no single Sonnet agent can land it in
one isolated-worktree run. Split, every piece is bounded, analytically
oracled, and sequenced foundations-first.

---

## 2. Current kernel state (verified at 4d4f42da — GK-P wiring complete)

> **Updated 2026-05-24.** T-104a..h shipped all pure-Python G3/zebra/class-A
> machinery.  GK-P01..P08 (Group W) then wired everything into the public
> `geom/__init__` façade and added `surfacing.py` ToolSpecs.  The table below
> reflects the current shipped state — not the original gap analysis.

| Area | Shipped state (post GK-P) |
|---|---|
| **Pure-Py G3 blend** | `blend_srf_g3` + `g3_blend_trim_sew` (GK-62) fully exported from `geom/__init__`; `curvature_rate_continuity_residual` oracle also exported. `feature_blend_srf_g3` ToolSpec in `surfacing.py` (GK-P01). |
| **Trim-by-curve** | OCCT worker path (`feature_trim_by_curve`) + pure-Python carrier-matrix path (GK-40) + **general NURBS×NURBS best-effort path (GK-P44)**: `trim_face_by_nurbs_ssi` uses the robust SSI (GK-P15) for arbitrary NURBS carriers, validate_body-clean for single-closed-loop cases. C2-T12 Section+prism fallback is still JS/WASM worker code (out of pure-Python scope); degenerate/multi-branch cases stay on the OCCT worker. |
| **Face imprint** | GK-19 analytic-matrix imprint shipped; general NURBS×NURBS stays OCCT worker (by design). |
| **Curvature combs** | `feature_surface_curvature_combs` — OCCT viz path + `include_g3_residuals` flag for pure-Python NurbsSurface targets (GK-P07); uses `curvature_rate_continuity_residual` oracle (GK-62). |
| **Zebra / reflection lines** | `zebra_stripe_continuity_analyser` (GK-38) + `reflection_lines` (GK-95) both exported from `geom/__init__`; `feature_zebra_analysis` ToolSpec in `surfacing.py` (GK-P02). |
| **Edge continuity report** | `edge_continuity_report` extended to G0/G1/G2/G3 via `curvature_rate_continuity_residual`. Global body audit via `continuity_audit` (GK-138) exported; `feature_global_continuity_audit` ToolSpec (GK-P04). |
| **Class-A harness** | `class_a_acceptance_harness` (GK-64) + `run_leading_pass` / `LeadingReport` (leading.py) exported from `geom/__init__`; `feature_class_a_check` ToolSpec (GK-P03). |
| **G3 chain blend** | `blend_edge_chain_g3` (GK-132) exported from `geom/__init__`; `feature_g3_chain_blend` ToolSpec (GK-P05). |
| **Surface fit (Patch)** | `fit_surface` (GK-34) exported from `geom/__init__`; `feature_fit_surface` ToolSpec (GK-P06). |

**Bottom line (post GK-P).** All T-104 deliverables are shipped and wired.
Pure-Python G3 blend, zebra analyser, class-A harness, global continuity audit,
and G3 chain blend are all invokable via the `.feature` workflow.
Curvature combs includes the G3 residual column for pure-Python surfaces.
The two former Phase-4 non-goals now have best-effort pure-Python coverage:
general NURBS×NURBS trim (GK-P44, `trim_face_by_nurbs_ssi`) and OCCT-path G3
(GK-P43, analyzer + pole round-trip).  Only the genuinely-impossible /
worker-owned remainders stay delegated: OCCT *native-enum* G3 (no `GeomAbs_G3`
token) and the degenerate/multi-branch trim cases + C2-T12 Section+prism
fallback (JS/WASM worker code).

---

## 3. The structural-impossibility call-outs (read this before writing scopes)

These are baked into the sub-task scopes/DoDs so no agent burns a run
chasing them:

1. **Algorithmic G3 in stock OCCT is impossible.** `GeomAbs_G3` is
   absent from the `GeomAbs_Shape` enum. No OCCT API (`BRepFilletAPI`,
   `GeomFill`, `ShapeUpgrade`, `GeomConvert`) can *enforce* or *report*
   G3. **Any sub-task touching OCCT for G3 must be visualization /
   approximation only** (eyeball via combs — already shipped). This is
   flagged on **T-104f** and **T-104g**.

2. **G3 *is* achievable in the pure-Python NURBS layer.** Third-
   derivative continuity of two NURBS surfaces meeting at a seam is
   closed-form math (homogeneous quotient rule, `nurbs.py`'s analytic
   derivatives from GK-02). The Kerf pure-Python kernel is *not* OCCT,
   so the OCCT enum limitation does not bind it. T-104b/T-104c deliver
   the **pure-Python** algorithmic G3 (roadmap `GK-62`). DoD oracle is
   analytic (third-derivative residual `< 1e-5` across a known join,
   comb-of-combs continuous), exactly matching `GK-62`.

3. **Pure-Python trimmed-solid round-trip is bounded but real.** GK-40
   (trim face by SSI curve) is a known long-tail item but it is *pure
   math* on top of the already-landed SSI (GK-09) + closest-point
   (GK-07) + brep_build (GK-13) + `boolean.py` imprint (GK-19). It is
   bounded for one agent if scoped to **plane / cylinder / sphere
   carrier surfaces** (the same analytic matrix `boolean.py` already
   supports) — *not* arbitrary NURBS×NURBS, which stays delegated to
   the OCCT worker. T-104d is scoped to that matrix; the general
   NURBS×NURBS trim explicitly stays on the OCCT worker path
   (`feature_trim_by_curve`) and is **out of T-104's pure-Python
   scope** — documented, not attempted.

4. **The OCCT worker trim fallback (C2-T12 Section+prism) is JS/WASM
   worker code**, not kernel. It is *out of scope* for T-104's
   pure-Python sub-tasks (and would collide with worker-owning agents);
   T-104e covers only the **pure-Python validation + side-selection
   contract** that the worker consumes, plus wiring the pure-Python
   `GK-40` result as the in-process answer when the carrier is in the
   analytic matrix (OCCT worker stays the fallback for everything else).

---

## 4. Sub-task dependency graph

```
        T-104a  (G3 residual oracle — pure-Python, foundation)
           |
           v
        T-104b  (pure-Python G3 blend strip — geom/blend_srf.py rebuild)
           |
           v
        T-104c  (G3 trims/sews to a Body — bounded matrix)
           |                                   \
           |                                    \
   T-104d  (GK-40 pure-Py trim-by-curve,         \
            plane/cyl/sphere carrier matrix)      \
           |                                       \
           v                                        v
   T-104e  (trim side-selection + validation     T-104f  (zebra / reflection-
            contract; wire GK-40 in-proc)                 line continuity analyser)
                                                          |
                                                          v
                                                  T-104g  (class-A acceptance
                                                           harness: combs+zebra+
                                                           G0..G3 gate)
                                                          |
                                                          v
                                                  T-104h  (class-A *leading*
                                                           workflow — hot-spot
                                                           flagging surface)

Foundations first:  T-104a → T-104b → T-104c   (the algorithmic-G3 spine, opus-grade math but each bounded)
Parallelisable:      T-104d (after GK-40 deps already landed) ‖ T-104f (after T-104a)
Gate + workflow:     T-104g depends on T-104a + T-104f ;  T-104h depends on T-104g
Worker contract:     T-104e depends on T-104c + T-104d
```

`Depends-on` uses **T-104** ids only where the dependency is *within
this epic*; where a sub-task builds on already-landed roadmap items
(GK-02 analytic derivatives, GK-07 closest-point, GK-09 SSI, GK-13
brep_build, GK-19 imprint, GK-24/25 G1/G2 blend) that is noted in the
Scope, not as a blocking `Depends-on` (those are shipped at 384f401).

---

## 5. Money / reach ranking (why this order)

T-104 is Tier-A P1 because it serves **two high-value personas**
(automotive Class-A surfacing, jewelry Class-A surfacing) and is the
kernel-depth opus-spine moat the §6 geometry-kernel thesis demands.
Within the split:

1. **T-104a/b/c (algorithmic G3 spine)** rank highest: this is the
   *only genuinely-new kernel capability* in the epic and the headline
   "G3" deliverable. Pure-Python, so it is real (not the OCCT
   eyeball-only path). Foundations — everything class-A leans on the
   residual oracle.
2. **T-104d/e (pure-Python trim-by-curve)** next: closes the GK-40
   long-tail and removes a hard OCCT coupling for the bounded analytic
   matrix; directly serves the jewelry "cut a stone-setting window"
   and automotive panel-trim workflows.
3. **T-104f/g/h (zebra + class-A gate + leading)** close the
   *workflow* gap — the deliverable users actually see ("flag the
   hot-spots on my fender"). Lower kernel-depth but high persona reach;
   sequenced last because the gate consumes the G3 residual oracle from
   T-104a.

---

## 6. Out of scope for T-104 (documented) — and the GK-P43/P44 best-effort updates

The two items below were the T-104 documented non-goals. The user asked to
attempt them best-effort; **GK-P43** and **GK-P44** (Group BE) delivered real
coverage *around* the impossible parts. The narrow truly-impossible boundary is
called out explicitly.

- General **NURBS×NURBS** trim-by-curve — **best-effort SHIPPED (GK-P44).**
  `geom/trim_curve.py` now extends beyond the plane/cyl/sphere carrier matrix:
  `trim_face_by_ssi` falls through to `trim_face_by_nurbs_ssi`, which uses the
  robust marching SSI (`intersection.surface_surface_intersect`, hardened by
  GK-P15 branch-stitching) to compute the trim curve for **arbitrary NURBS
  carriers**, wraps the closed SSI loop as a B-rep edge, splits + builds the
  trimmed NURBS face (interior disk for `keep_side='inside'`, natural boundary
  + SSI hole for `keep_side='outside'`), and asserts `validate_body(open=True)`
  is clean. DoD met for common (non-degenerate) cases: single closed interior
  loop → `validate_body`-clean trimmed face (`test_nurbs_trim_ssi_gkp44.py`,
  residual < 1e-5). T-104's analytic carrier-matrix trim stays the exact fast
  path. The OCCT worker (`feature_trim_by_curve`) **stays the documented
  fallback** for degenerate / elliptic-loop / multi-branch / open-loop /
  validate-failing cases — those are declined with an `unsupported-input`
  reason rather than silently producing an invalid face.
- The **C2-T12 Section+prism JS/WASM worker fallback** — worker code,
  owned elsewhere, would collide with concurrent agents (unchanged).
- **OCCT *native-enum* G3** — STILL IMPOSSIBLE. `GeomAbs_G3` is absent from
  `GeomAbs_Shape`; OCCT will never enforce/report G3 through its own
  machinery. This narrow part is NOT attempted.
- **Best-effort OCCT-path G3 — SHIPPED (GK-P43)**, bypassing the missing enum:
  (a) **analyzer** — sample `Geom_BSplineSurface.DN(u,v,nu,nv)` third
  derivatives (`occtBridge.sampleSurfaceThirdDeriv` /
  `occtWorker.opOcctG3Audit`, gated by `NURBS_PHASE4_G3_BINDINGS`, graceful
  `OcctG3UnsupportedError` degrade) → pure-Python
  `surface_analysis.occt_g3_residual_from_poles` dκ/ds oracle; surfaced per
  edge via `continuity_audit` `g3_residuals`. (b) **pole round-trip** —
  `surface_analysis.occt_g3_pole_roundtrip` extracts OCCT poles, runs the
  pure-Python G3 pole-adjustment (`match_srf` G3, GK-P10), writes poles back;
  DoD: OCCT-origin pair reports G3 residual `< 1e-5` after the round-trip.
  Pole/oracle math verified in-env on a `NurbsSurface` standing in for the
  extracted poles; the live `DN` / `SetPole` paths are deploy-gated (OCC not
  installed in CI).
- `src/routes/compare`, `docs/*.md` capability pages, migrations,
  kerf-cli — owned by other concurrent agents this session.
- Parasolid/ACIS, GPU/native geometry — non-goals at every phase
  (geometry-kernel-roadmap §6).

---

## 7. Mapping to the geometry-kernel roadmap

| T-104 sub-task | roadmap GK item(s) | roadmap status at 384f401 |
|---|---|---|
| T-104a | GK-62 (oracle half), GK-65 (comb numeric) | `[ ]` |
| T-104b | GK-62 (blend half) | `[ ]` |
| T-104c | GK-62 + GK-26-style trim/sew pattern | `[ ]` |
| T-104d | **GK-40** (trim face by SSI curve) | `[ ]` (opus) |
| T-104e | GK-40 wiring + GK-71 façade note | `[ ]` |
| T-104f | **GK-38** (zebra / reflection-line) | `[ ]` |
| T-104g | **GK-64** (class-A acceptance harness) | `[ ]` |
| T-104h | GK-64 follow-on (leading workflow) | new (product layer) |

These remain the single source of truth in
`geometry-kernel-roadmap.md`; T-104a..h are the *task-board* face of
the same work, sized for the ship-gate agent loop. Closing a T-104
sub-task should also tick its GK checkbox.

---

STATUS: COMPLETE — T-104 decomposed into T-104a..h, appended to tasks.md.
