# Automotive as a first-class persona — honest gap pass

**Status**: scoping doc (not a commitment). Last-touched: 2026-05-15.

## TL;DR

Automotive is **not a fifth front**. It rides almost entirely on the
existing P0 spine plus **one** automotive-specific build (Class-A
surfacing, `ROADMAP.md` row **P1-6**). Finish P0-2 (DWG/DXF), P0-3
(sheet metal), P0-5 (large-assembly → full-vehicle DMU) and P1-5
(NURBS-boolean robustness) and Kerf is already meaningfully
automotive-capable for **brackets / components / tooling / molds** —
which is most of the volume an automotive *engineer* (as opposed to a
*studio surfacer* or a *crash analyst*) actually touches day to day.

The deep automotive moats (Alias/ICEM-class Class-A, crash/NVH/CFD,
3D harness) are honestly out of reach for a solo founder in the near
term and are slotted at P1-6 / P1-7 / P2 with truthful status. The one
quick win inside the Class-A story is **zebra / reflection-line
analysis**, which is shader-side and lands without the deferred
custom-WASM G3 work.

This doc grounds every claim against the code state at commit
`f200000` (refactor branch).

---

## What genuinely transfers to automotive today (verified)

| Capability | Code evidence | Automotive use |
|---|---|---|
| NURBS surfacing (Phase 4): sweep1/2, networkSrf, blendSrf | `packages/kerf-cad-core/src/kerf_cad_core/surfacing.py` (`run_feature_sweep1/2`, `run_feature_network_srf`, `run_feature_blend_srf`); ops in `src/lib/occtWorker.js` | Component/trim/duct surfaces; *not* Class-A bodysides (see gap) |
| Surface continuity query/enforce | `surface_continuity` tool, `surfacing.py` — C0/C1/C2 (network) · G0/G1/G2 (blend) | Tangent/curvature checks on component surfaces |
| Curvature-comb visualization | `feature_surface_curvature_combs`, `surfacing.py`; `opSurfaceCurvatureCombs` in `occtWorker.js` | EYEBALL G2/G3 at seams — the standard *manual* Class-A inspection step |
| FEM linear-static + modal + steady thermal + bonded contact | `packages/kerf-fem/` — `analysis_type ∈ {linear_static, modal, thermal}` (`tools.py:56`), `_run_thermal` (`fenicsx_utils.py:578`), shared-node bonded contact | Bracket/mount stress + first-mode + simple thermal — *not* crash/NVH/durability |
| CAM 3-axis + 2.5D + 3D + 3+2 + 5-axis constant-tilt | `packages/kerf-cam/` (`five_axis/constant_tilt.py`, `tools.py` op enum) | Tooling, fixtures, mold/die machining |
| Parametric features, equations, configurations | shipped (`ROADMAP.md` Status overview) | Variant-driven component families |
| Chat-driven workflow + scripting SDK | `kerf-chat`, `kerf-sdk` | The differentiator — design intent in prose, automatable |

## What an automotive user CANNOT do today (verified gaps)

| Gap | Verified state | ROADMAP placement |
|---|---|---|
| **Class-A surfacing** (Alias / ICEM Surf / CATIA ICEM): algorithmic G2/G3, curvature-controlled surfaces, theoretical-vs-Class-A split | `surface_continuity` enum tops out at **C2/G2** (`surfacing.py`); **no `GeomAbs_G3`** in stock OCCT (comment `src/lib/occtWorker.js:3024-3034`); G3 is **viz-only** via curvature combs | **P1-6** (zebra/reflection shippable; algorithmic G3 = custom-WASM, deferred) |
| **Zebra / reflection-line analysis** | `grep` for `zebra`/`reflection-line`/`class-a` across `packages/` + `src/lib/` → **no hits** (only PCB `net_class` false-positives) | **P1-6** (the one near-term slice — shader-side) |
| **BIW / stamping sheet metal** (flange, hem, draw die, formability) | No `sheet_metal`/`flange`/`unfold`/`flat-pattern`/`k-factor` anywhere in `packages/` or `src/` | **P0-3** — automotive is the dominant consumer |
| **3D in-vehicle wiring harness** (route through DMU, bundle/segment/connector libs, formboard flatten, length/gauge/voltage-drop) | `kerf-wiring` is **WireViz YAML→SVG only** (`wireviz_runner.py` — 2D `.wiring` diagram); no 3D routing | **P1-7** |
| **Crash / impact (explicit dynamics), NVH, durability/fatigue, CFD, multibody** | FEM verified linear-static + modal + steady thermal + bonded contact only — no nonlinear/explicit/fatigue path (`packages/kerf-fem/`) | **P2** (rides generic nonlinear/CFD/fatigue line) |
| **Full-vehicle DMU** (10,000s of parts; sectioning, packaging studies, clash) | Large-assembly ceiling unmeasured (existing P0-5); automotive is the extreme case | **P0-5** (cross-ref) |
| **DWG/DXF** (2D control drawings, supplier exchange, homologation) | No DXF/DWG read or write anywhere (existing P0-2) | **P0-2** (cross-ref) |
| **GD&T / PMI model-based definition + homologation docs** | Drawing engine + GD&T frames exist; **model-driven** MBD callouts do not (shares P1-3) | **P2** (shares P1-3 "GD&T-from-model") |
| **EV-specific**: battery-pack packaging, busbar/HV routing, thermal | None | **P2** |

## Why P1-6 (Class-A) is the only automotive-specific spend

Everything else automotive needs is a gap the *other* personas already
have on the board (P0-2, P0-3, P0-5, P1-3, P1-5). Class-A is the one
thing no other Kerf persona forces. Even there it splits cleanly:

- **Zebra / reflection-line analysis** — environment-map / stripe
  shader on the tessellated surface in the existing Three.js viewport.
  No OCCT dependency, no WASM rebuild. This is the cheap credibility
  win and should ship first inside P1-6.
- **Algorithmic G2/G3 continuity enforcement** — structurally blocked
  in stock OCCT (`GeomAbs_G3` does not exist in the `GeomAbs_Shape`
  enum; confirmed by the existing in-code comment and by the
  `surface_continuity` enum). Needs either a custom WASM rebuild with a
  G3-aware constraint solver, or a Python nonlinear pole-adjustment
  approximation. This is the deliberately-deferred multi-year moat,
  consistent with how Phase-4 Capability 4 is already framed.

Until then the honest pitch is: *Kerf eyeballs G3 via curvature combs
(the standard manual Class-A check) but does not algorithmically
enforce it — round-trip to Alias/ICEM for final Class-A sign-off.*

## Recommendation

Do **not** open an automotive workstream. Finish the P0 spine
(P0-3 / P0-2 / P0-5 already prioritized for Mechanical/Architect) — it
delivers automotive component/tooling capability for free — and treat
**P1-6 zebra/reflection** as a small, high-signal add when an
automotive user actually shows up. Algorithmic G3, crash/NVH/CFD, 3D
harness, and EV packaging stay deferred with truthful status; chasing
them speculatively would harm the rest of the backlog and overclaim a
capability Kerf does not have.
