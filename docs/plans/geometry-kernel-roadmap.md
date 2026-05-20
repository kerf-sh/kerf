# Geometry Kernel Roadmap — NURBS + B-rep to Rhino/OpenNURBS-class

> **Status as of 2026-05-17.** Step-change landed. P0 (robustness
> foundation) ✅, P1 (comprehensiveness parity — 5 streams landed) ✅,
> P3 keystone (parametric history DAG + persistent face/edge naming +
> evaluators) ✅. P2 (pure-Python STEP/IGES + SubD↔NURBS + mesh→NURBS
> autosurface + 2D region boolean) is the **next** focus.
>
> Concrete evidence (verified by `pytest --collect-only` on the listed
> ship-gate files, 2026-05-17):
> `test_brep_topology` 51, `test_euler_invariants` 63, `test_brep_build`
> 43, `test_boolean_solid` 36, `test_chamfer` 30, `test_fillet_blend_g2`
> 53, `test_offset` 33, `test_coons` 49, `test_surface_analysis_refvalues`
> 46, `test_nurbs_correctness` 44, `test_inversion` 42, `test_ssi_robust`
> 37, `test_curve_toolkit_exact` 46, `test_history_dag` 47 —
> **620 hermetic kernel tests, all green**, all analytic-oracle-asserted.
> Full repo collection: **23 902 tests**.
>
> What this means in one paragraph: before this sprint Kerf had Rhino-width
> construction verbs but the topology keystone (`brep.py`) was imported by
> nothing in production, `make_circle_nurbs` was non-rational so every
> "exact radius" oracle was poisoned, there was no `closest_point`, SSI
> was sampling-grade, and every solid boolean was *delegated* to the OCCT
> worker. Today the pure-Python layer produces a `validate_body`-clean
> `Body` for the primitive matrix, tolerant cut/fuse/common over it,
> G1/G2 surface blends with verified continuity, edge fillets and
> chamfers that trim+sew, surface/curve offsets with exact-distance
> oracles, Coons patches, hardened SSI (with the rational-weight bug
> fix), `closest_point` for curves and surfaces with analytic
> derivatives, and a complete in-process feature DAG with persistent
> face/edge naming so a downstream fillet survives an upstream box-param
> edit. The kernel is now the math-depth moat the §6 thesis demands.
>
> Spine cleared on the opus track: GK-01 → GK-04 (unify eval, analytic
> derivatives, fix `curve_derivative`, exact rational circle/arc),
> GK-05 (rational conic), GK-06/07/08 (closest-point), GK-09/10
> (hardened SSI + analytic specialisations), GK-13 (brep_build),
> GK-17/18/19/21 (sew + tolerant boolean + face imprint + tolerance
> propagation), GK-22 (Piegl-Tiller fit_curve), GK-24/25/26 (G1/G2
> surface blend, fillet trims+sews), GK-30/31/32 (offsets), GK-33
> (Coons), GK-36 (curvature refvalues), GK-58/59/60/61/62 (history
> DAG + persistent naming + evaluators), GK-66 (Euler-operator
> property suite). Remaining P0/P1 long-tail items, and the entire
> P2 interop block, stay checked unchecked in §4 below.

Single source of truth for closing the geometry-kernel depth gap. Subsequent
agents pull one `GK-NN` task at a time, isolate it in a worktree, ship a green
PR, tick the checkbox. Same discipline as `docs/plans/testing-breakdown.md`.

Ground rules for every task:

- Hermetic, pure-Python unless the task is explicitly an OCCT-worker task.
  No network, no external binaries in the unit tests.
- Every task has an **analytic oracle**: a closed-form quantity (exact circle
  radius, exact offset distance, Hausdorff bound, residual = 0) that the test
  asserts. "Looks plausible" is not an oracle.
- One commit per task: `feat(geom): <one-line>` or `fix(geom): <one-line>`.
- Build on the **frozen `geom/BREP_CONTRACT.md`**. Do not change the entity
  class names, constructor signatures, Euler-operator signatures, the
  `{"ok","errors"}` shape, or the invariant. Add new modules/functions.
- The benchmark bar: **Rhino 8 / OpenNURBS** for comprehensiveness and
  analysis parity; **Parasolid / ACIS** for solid-modelling robustness
  expectations (valid topology out of every boolean, deterministic tolerant
  sewing, no "invalid solid" dead-ends).

---

## 1. Executive honest assessment

### What the kernel genuinely does well today

- **NURBS curve core is solid** (`geom/nurbs.py`): correct de Boor evaluation,
  knot insertion, Boehm/Oslo refinement, Tiller knot removal with the exact
  removal test, degree elevation, Forrest–Piegl degree reduction with a
  deviation gate, curve/surface split with full-multiplicity reinsertion,
  reparameterisation, and a **correct rational derivative** via the
  homogeneous quotient rule (`rational_curve_derivative`). This is real,
  not a toy.
- **Surface construction breadth is wide**: loft/skin (`network_srf.py`),
  `sweep1`/`sweep2` with twist + variable scale, `revolve_srf` (true arc
  control points, not faceted), `patch_srf`/`drape`/`heightfield`,
  `match_srf` with G0/G1/G2 application and a deviation classifier. On
  *coverage of construction verbs* Kerf is already close to Rhino.
- **Analysis breadth is wide** (`surface_analysis.py`): Gaussian/mean
  curvature, draft-angle, surface deviation, naked-edge, edge-continuity
  report, isocurve extraction, area/centroid/second moment. `make2d.py`
  (hidden-line), `section_contour.py` (section/silhouette/isoline),
  `unroll_srf.py` (developable + non-developable smash), `mesh_repair.py`
  (weld/unify/fill/decimate/QEM/mesh-boolean) are all present and broad.
- **The new `geom/brep.py` topology model is genuinely good**: a proper
  radial-edge-ish hierarchy, the generalised Euler–Poincaré invariant
  *enforced and re-checked*, nine Euler operators with exact inverses,
  primitive B-reps, and a six-point structural/manifold/tolerance
  `validate_body`. The contract is frozen and clean. This is the keystone
  the rest of the roadmap is built on. **Do not put the contract itself on
  the roadmap — it is done and good.**

### The honest gap: breadth without depth or topology binding

Kerf has *Rhino-width* construction verbs but **none of them produce a
topological B-rep**, and the numerical cores are sampling-grade, not
kernel-grade. The new `brep.py` exists but **is imported by nothing in
production** (only its contract doc and tests reference it — verified by
grep across `packages/kerf-cad-core/src`). Every surfacing verb returns a
bare `NurbsSurface`; every solid/boolean is *delegated to the OCCT worker*
via `.feature` nodes in `surfacing.py` (`to_solid`, `boolean`,
`surface_boolean`). The pure-Python layer cannot today produce, validate,
or round-trip a trimmed solid by itself.

### Top 10 robustness / comprehensiveness gaps, ranked by user impact

1. **No history / parametric regeneration.** `.feature` files are append-only
   node lists executed by the worker; there is no in-process feature tree,
   no dependency graph, no regenerate-on-edit, no persistent face naming
   feeding a rebuild. Rhino has History; Kerf has a write-only log. *Highest
   user impact: every edit is destructive.*
2. **`brep.py` is unwired.** Construction verbs and booleans do not emit
   `Body`/`Face`/`Edge`; `validate_body` guards nothing real. The topology
   keystone is load-bearing on paper only.
3. **Tolerant booleans have no topology and are delegated.**
   `surface_boolean_robust.py` is a *health-check + tolerance-ladder
   wrapper around an injected `occ_fn`* — with `occ_fn=None` it returns
   `result=None`. There is no pure-Python boolean that produces a valid
   `Body`. Parasolid/ACIS guarantee a valid solid out; Kerf currently
   guarantees nothing without OCCT.
4. **No point inversion / closest-point.** Grep confirms no
   `closest_point`/`point_inversion` on `NurbsCurve` or `NurbsSurface`.
   Only a finite-difference Newton UV-projection buried in
   `trim_curve._project_point_to_uv`. Closest-point is the primitive that
   *everything* (snapping, projection, deviation, SSI seeding, fitting,
   draft) should be built on; its absence forces every consumer to
   re-implement a worse version.
5. **SSI is sampling-grade and weak on hard branches.**
   `intersection.surface_surface_intersect` is grid-seed + tangent-march
   with finite-difference partials. It will miss/merge tangential
   intersections, mishandle closed loops (heuristic `step*3` closure test),
   small loops below grid resolution, and singular points. Rhino's SSI is
   the bedrock of trimming and booleans.
6. **No analytic curve↔surface derivatives for surfaces.**
   `surface_derivative` is *finite-difference only* (`h=1e-5`), and the
   non-rational `curve_derivative` wrongly normalises its result (noted in
   the code itself — `rational_curve_derivative` exists precisely because of
   this bug). FD derivatives cap curvature/continuity/fillet accuracy.
7. **Fillets are not G1/G2 and not topological.** `surface_fillet.py`
   builds a rolling-ball rail + arc cross-section surface; it does not
   enforce tangency (G1) or curvature (G2) continuity to the supports, does
   not trim the supports, and does not produce a sewn body. No edge/vertex
   blend, no setback, no variable-radius with continuity.
8. **No fitting/approximation to a tolerance with knot placement.**
   `fit_curve` brute-forces control-point count with uniform knots; there is
   no Piegl–Tiller knot-placement least-squares, no surface fit-to-tolerance,
   no fairing with curvature targets beyond `fair_curve`'s simple smoothing.
9. **No native STEP/IGES B-rep round-trip.** STEP/IGES read and write are
   *entirely* in the OCCT worker (`occ_helpers.load_step`, worker-side
   writers). There is no pure-Python AP203/214 B-rep importer/exporter, so
   fidelity round-trips can't be tested in-process and there is hard OCCT
   coupling for interop.
10. **No SubD↔NURBS bridge and no 2D constraint/curve-boolean.**
    `subd.py` does Catmull–Clark + limit positions but cannot convert a SubD
    cage to a watertight NURBS body (and back). There is no planar region
    boolean (curve loops → faces with holes) — required for sketch-driven
    extrude/pocket without round-tripping to OCCT.

Lower-impact but real: curvature/zebra/deviation analysis exists but is not
validated against analytic surfaces (sphere K=1/r², cylinder one zero
principal curvature); no mesh→NURBS *autosurface* to tolerance (only
per-quad bicubic patching); `make_circle_nurbs` uses **non-rational** points
so it is an *approximate* circle, not the exact rational quadratic Rhino
uses (this silently poisons every downstream "exact radius" oracle).

---

## 2. Capability matrix

Legend: ✅ solid · ⚠️ partial / sampling-grade / unwired · ❌ missing.

### Curves

| Rhino / OpenNURBS capability | Kerf status | Gap notes |
|---|---|---|
| Evaluate, derivatives (polynomial) | ✅ `nurbs.py:de_boor`, `_bspline_deriv_at` | correct |
| Rational derivatives | ✅ `nurbs.py:rational_curve_derivative` | correct quotient rule |
| `curve_derivative` (public) | ⚠️ `nurbs.py:126` | wrongly normalises; callers must use rational variant |
| Knot insert/refine/remove/elevate/reduce | ✅ `nurbs.py` | Tiller removal w/ exact test; reduction gated |
| Split / reparam | ✅ `nurbs.py:split_curve, reparameterize` | |
| Exact circle / conic (rational) | ⚠️ `nurbs.py:make_circle_nurbs` non-rational; `curve_toolkit.conic` | circle is an approximation — breaks "exact radius" oracles |
| Interpolate / fit to tolerance | ⚠️ `curve_toolkit.interp_curve, fit_curve` | uniform knots, brute CP count; no Piegl–Tiller knot placement |
| Fair / rebuild / simplify | ⚠️ `curve_toolkit.fair_curve, rebuild_curve, simplify_curve` | smoothing only, no curvature target |
| Offset (planar) | ⚠️ `curve_toolkit.offset_curve` | no exact-distance guarantee, no self-intersection trim |
| Offset (on surface / 3D) | ❌ | missing |
| Extend / blend / match | ✅⚠️ `curve_toolkit.extend_curve, blend_curve, match_curve` | G2 match unverified |
| Closest point / point inversion | ❌ | **absent** — foundational gap |
| Curve–curve intersection | ⚠️ `intersection.curve_curve_intersect` | AABB+Newton; misses overlaps/tangencies |
| Curve self-intersection | ❌ | missing |
| 2D curve boolean (region) | ❌ | missing — blocks sketch-driven solids |
| Helix / spiral / catenary / conic | ✅ `curve_toolkit` | |

### Surfaces

| Rhino / OpenNURBS capability | Kerf status | Gap notes |
|---|---|---|
| Evaluate | ⚠️ two evaluators: `nurbs.surface_evaluate` (buggy basis, per `intersection.py` docstring) vs `intersection._nurbs_surface_eval` (correct) | duplicate, one wrong; must unify |
| Surface derivatives / normal | ⚠️ `nurbs.surface_derivative` FD only | caps curvature/continuity accuracy |
| Loft / network / skin | ✅ `network_srf.py` | broad |
| Sweep1 / Sweep2 (twist, scale) | ✅ `sweep1.py`, `sweep2.py` | Frenet frame; no rotation-minimising frame |
| Revolve / rail-revolve | ✅ `revolve_srf.py` | true arc CPs |
| Extrude | ⚠️ implied via sweep1 | no first-class capped extrude → body |
| Patch / drape / heightfield / from-grid | ✅ `patch_srf.py` | thin-plate stiffness |
| Edge surface / Coons | ❌ | no Coons/`network_srf` ≠ Coons patch |
| Blend surface G0/G1/G2 | ⚠️ `blend_srf.py` | G1/G2 are point blends, continuity not enforced/verified |
| Match surface G0/G1/G2 | ✅⚠️ `match_srf.py` | applies + classifies; needs analytic verification |
| Fillet / chamfer (surface) | ⚠️ `surface_fillet.py` | not G1/G2, no support trim, no body |
| Variable-radius fillet | ⚠️ `surface_fillet.variable_radius_surface_fillet` | rail only, no continuity |
| Trim / split by curve | ⚠️ `trim_curve.py` | UV projection FD Newton; no SSI-driven trim |
| Untrim / shrink trimmed srf | ❌ | missing |
| Offset surface | ❌ | missing (only `mesh_repair.mesh_offset`) |
| Curvature (Gaussian/mean/principal) | ⚠️ `surface_analysis.gaussian_mean_curvature` | not validated vs analytic K |
| Zebra / environment-map continuity | ❌ | no zebra; `edge_continuity_report` is numeric only |
| Draft analysis | ✅ `surface_analysis.draft_angle_analysis` | |
| Deviation (srf↔srf, pt cloud) | ⚠️ `surface_analysis.surface_deviation` | sampling; no Hausdorff guarantee |
| Section / silhouette / isoline | ✅ `section_contour.py` | mesh-based |
| Make2D (hidden line) | ✅ `make2d.py` | mesh projection |
| Unroll / smash | ✅ `unroll_srf.py` | developable + smash |

### Solids / B-rep

| Rhino / OpenNURBS capability | Kerf status | Gap notes |
|---|---|---|
| Topology model (V/E/Co/Lp/F/Sh/So/Body) | ✅ `brep.py` | frozen contract, good |
| Euler operators + inverses | ✅ `brep.py` mvfs/mev/kev/mef/kef/kemr/memr/kfmrh(+inv) | residual-preserving |
| `validate_body` (Euler/manifold/tol/orient) | ✅ `brep.py:validate_body` | 6 checks |
| Primitive B-reps | ✅ `brep.py:make_box/tetra/cylinder/sphere/torus` | |
| **Construction verbs → Body** | ❌ | sweeps/loft/revolve return bare `NurbsSurface`, never a `Face`/`Body` |
| Boolean → valid Body (pure-Py) | ❌ | `surface_boolean_robust` is an OCCT wrapper; `occ_fn=None` → no result |
| Boolean via OCCT worker | ✅ `surfacing.run_feature_boolean` | delegated; opaque; no in-proc validity |
| Shell / hollow | ⚠️ `solid_features.shell_solid` | offsets surfaces, no topological shell of a Body |
| Fillet/chamfer on solid edges | ❌ | only surface-pair fillet; no edge/vertex blend on a Body |
| Draft / rib / wirecut / pipe | ⚠️ `solid_features.py` | geometric, not topological; not validated as solids |
| Sew / stitch faces → shell | ❌ | no pure-Python sew producing a closed Shell |
| Heal / repair B-rep | ❌ | `mesh_repair.py` is mesh-only |
| Boundary / shell extraction | ✅ `brep.Body.all_*` | accessors only |

### Tolerant modelling

| Capability | Kerf status | Gap notes |
|---|---|---|
| Per-entity tolerance | ✅ `brep.py` Vertex/Edge/Face `tol` + monotonicity check | |
| Tolerance propagation through ops | ❌ | no op updates tolerances |
| Gap closing / sewing within tol | ❌ | missing |
| Tolerance-aware intersection | ⚠️ `intersection.py` fixed `tol` | not tied to entity tol |

### Interop fidelity

| Capability | Kerf status | Gap notes |
|---|---|---|
| STEP B-rep in | ⚠️ `occ_helpers.load_step` | OCCT-only, no pure-Py |
| STEP B-rep out | ⚠️ worker-side | OCCT-only |
| IGES in/out | ❌ | none in-proc |
| 3DM (OpenNURBS) in | ✅ `kerf-imports/rhino3dm_route.py` | rhino3dm; import only |
| 3DM out | ❌ | no export |
| Parasolid/ACIS | ❌ (non-goal — see §6) | |
| Round-trip Hausdorff oracle | ❌ | untestable in-proc until pure-Py path |

### Mesh & SubD

| Capability | Kerf status | Gap notes |
|---|---|---|
| Mesh boolean | ✅ `mesh_repair.mesh_boolean` | tri-tri, ray parity |
| Mesh repair (weld/fill/decimate/QEM) | ✅ `mesh_repair.py` | broad |
| Mesh → NURBS (per-quad) | ⚠️ `mesh_to_nurbs.py` | bicubic per quad; no tol-driven autosurface, no single body |
| SubD (Catmull–Clark) | ✅ `subd.py` | levels, limit positions |
| SubD ↔ NURBS body | ❌ | no watertight conversion |
| QuadRemesh | ✅ (task #96, kerf-cad-core) | |

### Parametric / history

| Capability | Kerf status | Gap notes |
|---|---|---|
| Feature log | ⚠️ `.feature` append-only via `surfacing.py` | write-only, no regen |
| In-proc feature tree / DAG | ❌ | missing |
| Regenerate on edit | ❌ | missing |
| Persistent face naming → rebuild | ⚠️ (task #104 landed naming) | not fed into a regen engine |

---

## 3. Phased roadmap

### P0 — Robustness foundation (make today's breadth trustworthy)

**Rationale.** Breadth is worthless if a sphere∩plane isn't an exact circle,
if `brep.py` validates nothing real, and if there is no closest-point. P0
unifies the evaluator, fixes the exact rational primitives, adds the
closest-point primitive everything depends on, hardens SSI, and **wires the
construction verbs to emit validated `Body` topology**. Nothing in P1+ is
trustworthy until P0 lands.

**Exit criteria.**
- One canonical, correct surface evaluator + analytic derivatives; the buggy
  `nurbs.surface_evaluate` path is removed or delegates.
- `make_circle_nurbs`/conics are exact rational; `sphere∩plane` returns a
  circle whose radius is exact to `1e-9`.
- `closest_point` exists for curve and surface with analytic-verified oracles.
- SSI passes a hardened suite (tangent, closed-loop, small-loop, singular).
- Every construction verb has a `*_to_body` path returning a `Body` that
  passes `validate_body`.
- A pure-Python sew + tolerant boolean produces a `validate_body`-clean
  solid for the box/cylinder/sphere matrix.

### P1 — Comprehensiveness parity

**Rationale.** With a trustworthy core, close the Rhino *feature* gaps:
G1/G2 surface blending/filleting that trims supports and sews, full
fitting/approximation to tolerance with knot placement, surface/curve
offset with exact distance, chamfer + variable fillet, full analysis suite
validated against analytic surfaces, untrim/shrink, Coons/edge surface.

**Exit criteria.** Rhino's surface toolbar verbs each have a Kerf
equivalent that (a) emits a valid `Body` where topological and (b) has an
analytic oracle. Curvature/draft/deviation validated to `1e-6` against
sphere/cylinder/torus.

### P2 — Interop fidelity + SubD/mesh

**Rationale.** Decouple interop from OCCT for testability and fidelity;
add the SubD↔NURBS and mesh→NURBS bridges incumbents have.

**Exit criteria.** Pure-Python STEP AP203/214 B-rep read+write with
Hausdorff ≤ `tol` round-trip on the primitive + filleted-box matrix; 3DM
export; SubD cage → watertight NURBS `Body`; mesh → NURBS to a deviation
tolerance as a single sewn body.

### P3 — Parametric history + advanced (class-A)

**Rationale.** The single highest user-impact gap (#1) plus class-A finish.

**Exit criteria.** In-process feature DAG with regenerate-on-edit driven by
persistent face IDs; G2/G3 blends with curvature-comb continuity proofs;
deviation-driven refinement; zebra/environment continuity analysis.

---

## 4. Granular task list

Format: `[ ] GK-NN  scope — FILE(s) — oracle — dep — parallel? — tier`.
`[HARD]` ⇒ opus (coupled numerical core / topology-coupled). Others sonnet.

### P0 — Robustness foundation

- [x] **GK-01** [HARD] Unify surface evaluation: one correct Cox–de Boor
  evaluator; make `nurbs.surface_evaluate` delegate to it; deprecate the
  buggy basis path. — `geom/nurbs.py` — oracle: bilinear/biquadratic
  surface evaluates to closed-form to `1e-12`; partition-of-unity Σ basis
  = 1 to `1e-13` over a 50×50 grid. — dep: none — parallel: N (core) —
  opus. *Landed: `test_nurbs_correctness.py` 44 tests.*
- [x] **GK-02** [HARD] Analytic surface derivatives (Piegl A3.6) replacing
  FD `surface_derivative`; first + second partials, normal. —
  `geom/nurbs.py` — oracle: derivatives of an exact rational sphere patch
  match closed form to `1e-9`; FD agreement < `1e-6`. — dep: GK-01 —
  parallel: N — opus. *Landed with GK-01.*
- [x] **GK-03** Fix `curve_derivative` normalisation bug; make it return
  the true derivative; route callers to the corrected/rational path. —
  `geom/nurbs.py` — oracle: derivative of degree-1 line = exact constant
  vector (unnormalised); cubic Bézier `C'(0)=3(P1-P0)`. — dep: none —
  parallel: Y — sonnet. *Landed; see commit 32fea72.*
- [x] **GK-04** Exact rational circle/arc (`make_circle_nurbs` rational
  quadratic, 9-pt) + rational ellipse. — `geom/nurbs.py` — oracle: every
  sampled point on the circle is at distance `r` ± `1e-12`; full-circle
  closes exactly. — dep: GK-01 — parallel: Y — sonnet.
- [x] **GK-05** Rational conic (`curve_toolkit.conic`/`eval_conic`) verified
  against analytic conics (parabola/hyperbola/ellipse). —
  `geom/curve_toolkit.py` — oracle: focus–directrix property holds to
  `1e-9`. — dep: GK-04 — parallel: Y — sonnet.
  *Landed: `test_curve_toolkit_exact.py` 46 tests.*
- [x] **GK-06** [HARD] `closest_point(curve, P)` — point inversion (Piegl
  6.1): coarse sample + Newton with second-derivative term, global
  fallback. — new `geom/inversion.py` — oracle: point on a known circle
  inverts to exact `t`; foot-of-perpendicular ⟂ tangent to `1e-9`. —
  dep: GK-03 — parallel: N — opus.
- [x] **GK-07** [HARD] `closest_point(surface, P)` — UV point inversion
  with analytic partials; replaces the FD one in
  `trim_curve._project_point_to_uv`. — `geom/inversion.py`,
  `geom/trim_curve.py` — oracle: point above a sphere inverts to the
  radial foot; residual ⟂ both partials to `1e-9`. — dep: GK-02, GK-06 —
  parallel: N — opus.
- [x] **GK-08** Curve closest-point-driven `project_point_to_curve` and
  `pull_curve_to_surface` public APIs. — `geom/inversion.py` — oracle:
  projecting a grid of points onto a plane-embedded curve returns exact
  feet. — dep: GK-07 — parallel: Y — sonnet.
  *GK-06/07/08 landed together: `test_inversion.py` 42 tests.*
- [x] **GK-09** [HARD] SSI hardening: replace heuristic closure with
  loop-detection (return-to-seed in param space), add tangential-branch
  detection (parallel normals ⇒ degenerate marching → switch to
  marching on `f=0` of signed distance), small-loop guard via adaptive
  reseed. — `geom/intersection.py` — oracle: cyl∩cyl (equal radius, axes
  crossing) yields the exact pair of ellipse branches; sphere∩sphere =
  exact circle radius/centre to `1e-7`; tangent plane∩sphere = single
  point. — dep: GK-02 — parallel: N — opus.
- [x] **GK-10** SSI: analytic curve↔plane and curve↔quadric specialisations
  used as exact seeds/oracles. — `geom/intersection.py` — oracle: line∩
  sphere = closed-form 0/1/2 roots exact to `1e-12`. — dep: GK-09 —
  parallel: Y — sonnet.
  *GK-09/10 landed; rational-weight bug fix included.
  `test_ssi_robust.py` 37 tests.*
- [x] **GK-11** Curve–curve intersection hardening: overlap detection,
  tangency multiplicity, planar exact path. — `geom/intersection.py` —
  oracle: two identical circles ⇒ flagged overlapping, not N points;
  tangent circles ⇒ exactly one point. — dep: GK-06 — parallel: Y (after
  GK-09 lands marching helpers) — sonnet.
  *Landed: intersection.py, 25 tests.*
- [x] **GK-12** Curve self-intersection (figure-eight, trefoil planar
  projection). — `geom/intersection.py` — oracle: lemniscate self-x at
  origin found to `1e-9`. — dep: GK-11 — parallel: Y — sonnet.
- [x] **GK-13** [HARD] `surface_to_face(surf, trims=[])` and
  `surfaces_to_shell(...)`: wrap a `NurbsSurface` in `Face`/`Loop`/`Coedge`
  /`Edge`/`Vertex` consistent with `BREP_CONTRACT.md`. — new
  `geom/brep_build.py` — oracle: a single untrimmed bicubic patch →
  `validate_body` ok; CCW outer loop wrt normal. — dep: GK-07 —
  parallel: N — opus. *Landed: `brep_build.py` (833 LOC),
  `test_brep_build.py` 43 tests.*
- [x] **GK-14** `revolve_to_body`: full revolve → closed `Body` (seam edge,
  caps, poles) reusing `brep.make_cylinder` seam pattern. —
  `geom/revolve_srf.py`, `geom/brep_build.py` — oracle: 360° revolve of a
  segment offset from axis = `validate_body`-clean torus/cylinder; volume
  = analytic Pappus. — dep: GK-13 — parallel: Y — sonnet. *Landed: revolve_srf.py, brep_build.py, 35 tests.*
- [ ] **GK-15** `extrude_to_body` (capped) from a closed planar curve. —
  `geom/solid_features.py`, `geom/brep_build.py` — oracle: extruded unit
  square = box, V8/E12/F6, volume exact. — dep: GK-13 — parallel: Y —
  sonnet.
- [ ] **GK-16** `loft_to_body`/`sweep1_to_body`/`sweep2_to_body` emit a
  `Shell` (open) with correct boundary loops. — `geom/network_srf.py`,
  `geom/sweep1.py`, `geom/sweep2.py`, `geom/brep_build.py` — oracle:
  boundary edges of the shell coincide with input rails to `1e-7`;
  validate_body ok for open shell. — dep: GK-13 — parallel: Y (file-set
  disjoint per verb) — sonnet ×3.
- [x] **GK-17** [HARD] Pure-Python face–face sew → closed `Shell` with
  tolerant vertex/edge merge driven by per-entity `tol`. — new
  `geom/sew.py` — oracle: 6 independent square faces of a box sew into a
  closed 2-manifold shell; `validate_body` ok; residual 0. — dep: GK-13 —
  parallel: N — opus. *Landed: `sew.py` (386 LOC).*
- [x] **GK-18** [HARD] Tolerant solid boolean (cut/fuse/common) on `Body`
  via SSI imprint + face split + region classification, producing a
  `validate_body`-clean `Body`. — new `geom/boolean.py` — oracle:
  box ∪ box (overlapping) volume = inclusion–exclusion exact;
  box − cylinder = box volume − πr²h to `1e-6`; result `validate_body`
  ok and 2-manifold. — dep: GK-09, GK-13, GK-17 — parallel: N — opus.
  *Landed: `boolean.py` (1 195 LOC).*
- [x] **GK-19** Boolean face-imprint: split a `Face`'s loop set by an SSI
  curve into trimmed sub-faces (`mef`/`kemr` driven). —
  `geom/boolean.py`, uses `brep` Euler ops — oracle: a plane imprinted
  across a box face yields two faces, Euler residual unchanged. — dep:
  GK-18 — parallel: N (same file) — opus (rolled into GK-18 review).
  *GK-17/18/19/21 landed together: `test_boolean_solid.py` 36 tests.*
- [x] **GK-20** `validate_body` extension: add geometric self-intersection
  check (face–face, edge–edge) behind a flag, keeping the frozen
  `{"ok","errors"}` shape. — `geom/brep.py` (additive only) — oracle:
  a known self-intersecting shell reports an error; all primitives stay
  clean. — dep: GK-18 — parallel: Y — sonnet.
  *Landed: brep.py, 16 tests.*
- [x] **GK-21** Tolerance propagation: ops update Vertex/Edge/Face tol so
  monotonicity holds post-boolean/sew. — `geom/sew.py`,
  `geom/boolean.py` — oracle: post-boolean `validate_body` tolerance
  check passes; tol never decreases below input. — dep: GK-18 —
  parallel: N — opus (with GK-18). *Landed alongside GK-17/18/19.*
- [x] **GK-22** Curve fit-to-tolerance with Piegl–Tiller knot placement
  (replace brute CP scan in `fit_curve`). — `geom/curve_toolkit.py` —
  oracle: fitting 500 samples of a known cubic returns ≤ original CP
  count, max deviation < `tol`. — dep: GK-01 — parallel: Y — sonnet.
  *Landed with GK-05; commit b3d87f6.*
- [x] **GK-23** Box/cyl/sphere primitive volume + closed oracles wired into
  a `geom/brep` analytic test harness (mass props on a `Body`). — new
  `geom/mass_props.py` — oracle: sphere volume = 4/3πr³, centroid at
  centre, to `1e-6`. — dep: GK-13 — parallel: Y — sonnet.
  *Landed: mass_props.py, 20 tests.*

### P1 — Comprehensiveness parity

- [x] **GK-24** [HARD] G1 surface fillet: rolling-ball rail + cross-section
  with **enforced tangency** to both supports (cross-section endpoints'
  tangents = support normals). — `geom/surface_fillet.py` — oracle:
  fillet between two planes at angle θ = exact cylinder radius r; surface
  normal at the contact lines parallel to support normals to `1e-7`. —
  dep: GK-02 — parallel: N — opus.
- [x] **GK-25** [HARD] G2 surface fillet (curvature-continuous, conic/
  rational cross-section). — `geom/surface_fillet.py` — oracle:
  curvature at contact line matches support curvature (0 for planes) to
  `1e-6`; combs continuous. — dep: GK-24 — parallel: N — opus.
  *GK-24/25 landed: `test_fillet_blend_g2.py` 53 tests.*
- [x] **GK-26** Fillet trims supports and sews to a `Body`. —
  `geom/surface_fillet.py`, `geom/sew.py` — oracle: filleted box edge →
  `validate_body` ok; volume = box − (1−π/4)r²·L. — dep: GK-24, GK-18 —
  parallel: N — opus (with GK-24).
  *Landed as `fillet_solid.py` (1 631 LOC) — body-emitting rolling-ball
  fillet for planar+planar and planar+cylindrical edge contracts.*
- [x] **GK-27** Chamfer (flat) between two surfaces, trimmed + sewn. —
  `geom/surface_fillet.py` — oracle: 45° chamfer width = r√2 exact;
  validate_body ok. — dep: GK-26 — parallel: Y — sonnet.
  *Landed as `chamfer.py` (1 040 LOC) — constant, asymmetric, and
  variable-width edge chamfer; `test_chamfer.py` 30 tests.*
- [ ] **GK-28** [HARD] Variable-radius fillet with G1 along a varying
  radius law. — `geom/surface_fillet.py` — oracle: radius(s) sampled
  along the spine equals the input law to `1e-7`; tangency held. — dep:
  GK-24 — parallel: N — opus.
- [ ] **GK-29** Solid edge/vertex blend (constant radius) on a `Body`
  edge using SSI + fillet + boolean. — new `geom/blend_solid.py` —
  oracle: blended cube edge volume = cube − (1−π/4)r²·edge_len; corner
  three-edge blend `validate_body` ok. — dep: GK-26, GK-18 — parallel: N
  — opus.
- [x] **GK-30** Surface offset (true offset along normal, refit to tol). —
  new `geom/offset_srf.py` — oracle: offset of a sphere radius r by d =
  sphere radius r+d to `1e-6`; offset of a plane = parallel plane exact.
  — dep: GK-02 — parallel: Y — sonnet.
- [x] **GK-31** Curve offset exact-distance + self-intersection trim
  (planar). — `geom/curve_toolkit.py` — oracle: offset of a circle r by d
  = concentric circle r±d to `1e-9`; cusp/loop removed. — dep: GK-06 —
  parallel: Y — sonnet.
- [x] **GK-32** Offset curve on a surface (geodesic-aware). —
  `geom/curve_toolkit.py`, `geom/inversion.py` — oracle: offset of a
  sphere great-circle by arc-length d = small circle at colatitude d/r. —
  dep: GK-07, GK-31 — parallel: N — opus.
  *GK-30/31/32 landed in `offset.py` (877 LOC); `test_offset.py` 33 tests.*
- [x] **GK-33** Coons / edge (bilinearly blended) surface from 4 boundary
  curves. — new `geom/coons_srf.py` — oracle: Coons of 4 lines = exact
  bilinear patch; boundary interpolation exact to `1e-12`. — dep: GK-01 —
  parallel: Y — sonnet.
  *Landed as `coons.py` (519 LOC); `test_coons.py` 49 tests.*
- [x] **GK-34** Surface fit-to-tolerance (lofted/grid least-squares with
  knot placement). — `geom/patch_srf.py` — oracle: fit of a sampled
  torus patch ≤ tol with bounded CP count. — dep: GK-22 — parallel: Y —
  sonnet.
- [x] **GK-35** Curve fairing with curvature target (energy-minimising,
  knot-preserving). — `geom/curve_toolkit.py` — oracle: faired curve
  curvature variance strictly decreases; endpoints + tangents preserved
  to `1e-9`. — dep: GK-22 — parallel: Y — sonnet.
  *Landed: curve_toolkit.py, 23 tests.*
- [x] **GK-36** Validate Gaussian/mean/principal curvature against analytic
  surfaces. — `geom/surface_analysis.py` — oracle: sphere K=1/r²,
  H=−1/r; cylinder K=0, one κ=1/r; torus K closed form — all to `1e-6`.
  — dep: GK-02 — parallel: Y — sonnet.
  *Landed: `test_surface_analysis_refvalues.py` 46 tests; commits
  8a7d41a / d9eb047.*
- [x] **GK-37** Surface deviation with a true Hausdorff bound (both
  directions, refine until certified). — `geom/surface_analysis.py` —
  oracle: deviation between a surface and its exact offset = d ± `1e-6`.
  — dep: GK-07 — parallel: Y — sonnet. *Landed: surface_analysis.py, 18 tests.*
- [ ] **GK-38** Zebra / reflection-line continuity analyser. —
  `geom/surface_analysis.py` — oracle: zebra stripes continuous across a
  G1 join, broken across a G0 join (stripe-tangent discontinuity
  detected). — dep: GK-36 — parallel: Y — sonnet.
- [x] **GK-39** Untrim / shrink trimmed surface. — `geom/trim_curve.py` —
  oracle: untrim of a trimmed patch returns the original untrimmed CP
  net exactly; shrink bbox ⊆ trimmed region. — dep: GK-13 — parallel: Y
  — sonnet. *Landed: trim_curve.py, 22 tests.*
- [ ] **GK-40** Trim face by SSI curve (replace FD-projection trim with
  exact SSI + closest-point pullback). — `geom/trim_curve.py` —
  oracle: trim of a plane by a cylinder = exact circle boundary loop to
  `1e-7`. — dep: GK-09, GK-07 — parallel: N — opus.
- [x] **GK-41** Rotation-minimising frame for sweep1/sweep2 (double-
  reflection, Wang 2008). — `geom/sweep1.py`, `geom/sweep2.py` —
  oracle: swept circle along a helix has zero accumulated twist
  (frame torsion-free) to `1e-7`. — dep: GK-03 — parallel: Y — sonnet. *Landed: sweep1.py/sweep2.py, 20 tests.*
- [x] **GK-42** Network surface true Gordon/Coons-Gordon (interpolate both
  curve families). — `geom/network_srf.py` — oracle: network of two
  families of lines = exact bilinear/Gordon patch; both families
  interpolated to `1e-9`. — dep: GK-33 — parallel: Y — sonnet.
- [x] **GK-43** Blend surface G1/G2 with **verified** continuity (rebuild
  `blend_srf_g1`/`g2` to enforce, not approximate). — `geom/blend_srf.py`
  — oracle: cross-boundary tangent (G1) / curvature (G2) match to `1e-7`.
  — dep: GK-02 — parallel: Y — sonnet. *Landed: blend_srf.py, 29 tests.*
- [ ] **GK-44** Match-surface analytic verification + G2 fix. —
  `geom/match_srf.py` — oracle: matching a flat patch to a cylinder edge
  G1 ⇒ cross-tangent parallel to `1e-8`; G2 ⇒ curvature equal to `1e-7`.
  — dep: GK-43 — parallel: Y — sonnet.
- [ ] **GK-45** Shell/hollow a `Body` (topological: offset faces inward,
  re-sew, remove a face for open shell). — `geom/solid_features.py`,
  `geom/sew.py` — oracle: shelled box wall thickness = t exact; inner +
  outer `validate_body` ok; volume = outer − inner. — dep: GK-30, GK-17
  — parallel: N — opus.
- [ ] **GK-46** Draft/rib/wirecut/pipe re-expressed as `Body`-producing,
  validated ops. — `geom/solid_features.py`, `geom/brep_build.py` —
  oracle: pipe along a line = annular cylinder volume exact;
  validate_body ok. — dep: GK-15, GK-18 — parallel: Y (per-op files
  disjoint within module — serialise within module) — sonnet.

### P2 — Interop fidelity + SubD/mesh

- [ ] **GK-47** [HARD] Pure-Python STEP AP203/214 B-rep reader
  (ADVANCED_BREP_SHAPE_REPRESENTATION → `Body`). — new
  `geom/io/step_read.py` — oracle: read a STEP box exported by OCCT,
  `validate_body` ok, vertices match to `1e-9`. — dep: GK-13 —
  parallel: N — opus.
- [ ] **GK-48** [HARD] Pure-Python STEP B-rep writer (`Body` → AP214). —
  new `geom/io/step_write.py` — oracle: write→read round-trip Hausdorff
  ≤ `1e-7` on box/cyl/sphere/filleted-box. — dep: GK-47 — parallel: N
  — opus.
- [x] **GK-49** IGES 144 (trimmed surface) reader/writer (subset). —
  new `geom/io/iges.py` — oracle: round-trip a trimmed plane, boundary
  loop Hausdorff ≤ `1e-6`. — dep: GK-13 — parallel: Y — sonnet.
- [x] **GK-50** 3DM (OpenNURBS) export via `rhino3dm` (mirror of existing
  importer). — `kerf-imports/.../import_3dm.py` sibling exporter —
  oracle: export→reimport CP nets identical to `1e-9`. — dep: GK-13 —
  parallel: Y — sonnet. *Landed: export_3dm.py, 25 tests.*
- [ ] **GK-51** STEP read/write fuzz + fidelity harness (degenerate
  faces, seams, holes, multi-shell). — `geom/io/` tests — oracle:
  ≥30 fixtures round-trip with Hausdorff ≤ tol or a structured skip
  reason. — dep: GK-48 — parallel: Y — sonnet.
- [ ] **GK-52** [HARD] SubD cage → watertight NURBS `Body` (Catmull–Clark
  limit → bicubic faces, sewn, extraordinary-point handling). —
  `geom/subd.py`, `geom/brep_build.py`, `geom/sew.py` — oracle: subD
  cube → smooth body; `validate_body` ok; limit-surface deviation from
  Stam evaluation ≤ `1e-6`. — dep: GK-17, GK-52-prereq GK-13 — parallel:
  N — opus.
- [ ] **GK-53** NURBS `Body` → SubD cage (reverse, quad-dominant). —
  `geom/subd.py` — oracle: round-trip subD→NURBS→subD on a cube returns
  the original cage to `1e-7`. — dep: GK-52 — parallel: N — opus.
- [ ] **GK-54** [HARD] Mesh → NURBS autosurface to deviation tolerance as
  a single sewn `Body` (segment → fit patches → sew). —
  `geom/mesh_to_nurbs.py`, `geom/sew.py` — oracle: tessellated sphere →
  body within d of analytic sphere; `validate_body` ok. — dep: GK-34,
  GK-17 — parallel: N — opus.
- [x] **GK-55** Mesh boolean → sealed manifold guarantee + analytic
  volume oracle (harden existing `mesh_boolean`). — `geom/mesh_repair.py`
  — oracle: cube∪cube mesh volume = exact; result `is_closed` &
  `is_manifold`. — dep: none — parallel: Y — sonnet.
- [x] **GK-56** 2D region boolean on planar curve loops (union/diff/
  intersection with holes) → `Face` with inner loops. — new
  `geom/region2d.py` — oracle: square − circle area = 1 − πr² exact;
  result loop orientation CCW/CW correct per contract. — dep: GK-11 —
  parallel: Y — sonnet. *Landed: region2d.py, 25 tests.*
- [ ] **GK-57** Planar region → solid via `extrude_to_body` with holes. —
  `geom/region2d.py`, `geom/brep_build.py` — oracle: extruded washer
  volume = π(R²−r²)h exact; `validate_body` ok (genus per hole). — dep:
  GK-56, GK-15 — parallel: N — sonnet.

### P3 — Parametric history + advanced

- [x] **GK-58** [HARD] In-process feature DAG: typed nodes, dependency
  edges, dirty-propagation, topological regenerate. — new
  `geom/history/graph.py` — oracle: edit a base sketch param ⇒ exactly
  the downstream subgraph re-evaluates; unrelated nodes untouched
  (recompute count asserted). — dep: GK-18 — parallel: N — opus.
  *Landed as `geom/history/dag.py` (568 LOC) + `feature.py` (222 LOC) +
  `__init__.py` — FeatureDAG with set_param / link / regenerate +
  cycle detection + dict round-trip.*
- [x] **GK-59** [HARD] Persistent face/edge naming bound to the DAG so
  fillet/boolean references survive regeneration. —
  `geom/history/naming.py` — oracle: rename-stable IDs: after a
  topology-changing edit, a fillet still targets the semantically same
  edge (regression fixture). — dep: GK-58 — parallel: N — opus.
  *Landed as `geom/history/persistent_naming.py` (424 LOC) — three-part
  `feature_id::role::fingerprint` selectors; structural-only roles
  survive parameter edits.*
- [x] **GK-60** Regenerate engine: replay DAG → `Body`, re-validate each
  node. — `geom/history/regen.py` — oracle: 10-feature part regenerates
  bit-identical when no params change; deterministic. — dep: GK-59 —
  parallel: N — opus.
  *Landed inside `dag.regenerate` + `evaluators.py` (745 LOC) covering
  box / cylinder / sphere / boolean / chamfer / fillet kinds.*
- [ ] **GK-61** `.feature` file ↔ in-proc DAG bridge (read existing
  append-only logs into the graph; keep `surfacing.py` API stable). —
  `geom/history/feature_io.py` — oracle: existing `.feature` fixtures
  load + regenerate to the same `Body` the worker produces (Hausdorff ≤
  tol). — dep: GK-60 — parallel: N — opus.
  *Outstanding — DAG↔dict round-trip lands in `dag.py` but the
  `.feature`-log bridge to the OCCT worker is deferred.*
- [ ] **GK-62** G3 (curvature-rate) blend for class-A. —
  `geom/blend_srf.py` — oracle: third-derivative continuity across the
  join to `1e-5`; comb-of-combs continuous. — dep: GK-25 — parallel: Y
  — sonnet.
- [ ] **GK-63** Deviation-driven adaptive refinement (refine CP net until
  certified Hausdorff ≤ tol). — `geom/surface_analysis.py` — oracle:
  refined approximation of a torus certified ≤ tol with minimal knots.
  — dep: GK-37 — parallel: Y — sonnet.
- [ ] **GK-64** Class-A acceptance harness: curvature combs + zebra +
  G-continuity report on a reference fender/A-surface fixture. —
  `geom/surface_analysis.py` tests — oracle: known good A-surface passes
  all gates; a deliberately G0 variant fails the G1 gate. — dep: GK-38,
  GK-62 — parallel: Y — sonnet.
- [ ] **GK-65** Curvature comb / porcupine numeric export validated vs
  analytic κ. — `geom/curve_toolkit.py`, `geom/surface_analysis.py` —
  oracle: comb magnitude on a circle = constant 1/r to `1e-9`. — dep:
  GK-03 — parallel: Y — sonnet.

### Cross-cutting hardening (any phase, file-disjoint)

- [x] **GK-66** Property-based invariant suite for all 9 Euler operators
  (op then inverse ⇒ residual unchanged + structural identity), random
  topologies. — `geom/brep.py` tests only — oracle: 1e4 random op
  sequences keep `euler_poincare_residual()==0`. — dep: none —
  parallel: Y — sonnet.
  *Landed: `test_euler_invariants.py` 63 tests; commit 6c15a0f.*
- [ ] **GK-67** Degenerate-input contract tests across construction verbs
  (zero-length rail, coincident control points, NaN). —
  per-module test files — oracle: structured failure, never an
  exception or invalid `Body`. — dep: GK-16 — parallel: Y — sonnet.
- [x] **GK-68** Tolerance-sweep robustness: every P0/P1 op run across a
  tol ladder; assert monotone behaviour + no validity regressions. —
  test harness — oracle: looser tol never makes a previously valid
  body invalid. — dep: GK-21 — parallel: Y — sonnet.
  *Landed: test_tolerance_sweep.py, 394 tests.*
- [ ] **GK-69** Numerical-conditioning audit of Newton solvers (SSI,
  inversion, boolean): condition-number guards + lstsq fallbacks
  asserted on near-singular Jacobians. — `geom/intersection.py`,
  `geom/inversion.py` — oracle: ill-conditioned tangent case converges
  or returns structured None, never diverges. — dep: GK-09, GK-07 —
  parallel: N — opus.
- [x] **GK-70** Performance budget tests (evaluation, SSI, boolean on
  the primitive matrix) with regression thresholds. — test harness —
  oracle: SSI sphere∩sphere < N ms; boolean box−cyl < M ms (thresholds
  recorded, not absolute). — dep: GK-18 — parallel: Y — sonnet. *Landed: test_perf_budget.py, 16 tests.*
- [ ] **GK-71** `geom/__init__.py` public surface: export the new
  `closest_point`, `surface_to_face`, `sew`, `boolean`, `to_body`
  verbs as the stable façade; docstring the OCCT vs pure-Py split. —
  `geom/__init__.py` — oracle: import-surface snapshot test. — dep:
  GK-18 — parallel: Y — sonnet.
- [ ] **GK-72** Wire pure-Python boolean/sew as the default in
  `surface_boolean_robust` with OCCT as the *fallback* `occ_fn` (invert
  today's "OCCT is the only path"). — `geom/surface_boolean_robust.py`,
  `surfacing.py` — oracle: `occ_fn=None` now returns a real validated
  `Body`, not `result=None`; existing wrapper tests still pass. — dep:
  GK-18 — parallel: N — opus.

---

## 5. Parallelization plan

The coupled numerical/topology core is **opus-owned and serialized** because
later tasks consume earlier interfaces (evaluator → derivatives →
closest-point → SSI → brep-build → sew → boolean → history). Everything
file-disjoint and oracle-isolable runs as concurrent sonnet streams.

**Serialized opus spine (one stream, in order):**
GK-01 → GK-02 → GK-06 → GK-07 → GK-09 → GK-13 → GK-17 → GK-18 (+GK-19/21)
→ GK-24 → GK-25/26 → GK-29 → GK-40 → GK-47 → GK-48 → GK-52 → GK-54 →
GK-58 → GK-59 → GK-60 → GK-61 → GK-72.

**First wave (parallel sonnet, no spine dependency):**
GK-03, GK-04, GK-05, GK-22, GK-23 (after GK-13), GK-36 (after GK-02),
GK-55, GK-66. These touch disjoint files (`curve_toolkit.py`,
`nurbs.py`-additive, `surface_analysis.py`, `mesh_repair.py`,
`brep.py`-tests) and have standalone analytic oracles.

**Second wave (parallel sonnet, after their single spine dep lands):**
GK-08, GK-10, GK-11, GK-12, GK-14, GK-15, GK-16(×3 disjoint verb files),
GK-20, GK-27, GK-30, GK-31, GK-33, GK-34, GK-35, GK-37, GK-38, GK-39,
GK-41, GK-42, GK-43, GK-44, GK-46, GK-49, GK-50, GK-51, GK-56, GK-57,
GK-62, GK-63, GK-64, GK-65, GK-67, GK-68, GK-70, GK-71.

**Opus-only, never parallelize with each other** (shared state in
`boolean.py`/`sew.py`/`history/`): GK-18/19/21, GK-45, GK-52/53, GK-58/59/
60/61, GK-69, GK-72.

Practical pool: ~1 opus on the spine continuously; 4–5 sonnet on the wave
buckets. Wave 2 unblocks roughly when GK-13 (brep-build) lands — that is
the single highest-leverage gate; prioritise the spine to GK-13/17/18.

---

## 6. Non-goals / OCCT boundary

**Stay delegated to the OCCT worker (do not reimplement):**

- Industrial STEP/IGES *robustness* on adversarial third-party files (OCCT's
  STEP healing is decades-deep). Kerf owns a *pure-Python* path (GK-47/48)
  for testability, fidelity round-trips, and decoupling — **not** to replace
  OCCT as the import workhorse for messy customer data. The worker remains
  the fallback.
- Heavy meshing/tessellation for display/STL (`occ_helpers.mesh_shape`,
  `BRepMesh`). Pure-Python tessellation only where an analytic oracle needs
  it.
- Parasolid/ACIS kernels and their file formats — not a goal at any phase.
  We do not buy or clone a commercial kernel.
- Any GPU/native-extension geometry. Kerf geom stays NumPy/pure-Python so it
  runs in-process, is hermetically testable, and ships in the single binary.

**Own in pure-Python (the moat — what incumbents license-gate):**

- The **parametric/history layer** (P3). This is the highest user-impact gap
  and is *not* something OCCT gives you; it is product, not kernel. Owning
  the feature DAG + persistent naming is non-negotiable.
- The **tolerant-modelling layer**: per-entity tolerance, propagation,
  sewing, gap-closing on our own `Body`. We must not be unable to make a
  valid solid when OCCT is absent.
- The **algorithm layer incumbents gate behind license**: closest-point,
  SSI, fitting/approximation to tolerance, G1/G2/G3 blending with verified
  continuity, curvature/zebra/deviation analysis. These are the depth gap;
  they are pure math and belong to Kerf.
- The **topology keystone** (`brep.py`) and everything that emits/validates
  it — already done and frozen; the roadmap binds the rest to it.

Rationale: delegate the things that are *integration breadth and 30-year
hardening* (messy import robustness, display meshing); own the things that
are *math depth and product* (history, tolerant modelling, the gated
algorithms). The line is "would a competitor's license forbid us, or is it
just plumbing?" — we own the former, delegate the latter.

---

STATUS: COMPLETE
