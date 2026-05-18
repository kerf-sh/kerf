---
slug: nx
competitor: Siemens NX
category: cad-mechanical
left: kerf
right: nx
hero_tagline: "NX defined advanced surfacing for a generation — Kerf makes that power accessible without a six-figure licence."
---

# Kerf vs Siemens NX

Siemens NX (formerly Unigraphics) is one of the most capable high-end mechanical CAD, CAM, and CAE platforms ever built. It powers turbine blade design, automotive body engineering, and aerospace tooling. Its synchronous technology — a hybrid of parametric history and direct editing — set the standard for flexible B-rep manipulation. Its pricing reflects that capability: NX is enterprise software with enterprise pricing, typically negotiated through Siemens Digital Industries resellers. Kerf is the MIT-licensed alternative for engineers who need serious precision work without the enterprise price tag.

## Where they converge

Both NX and Kerf are built on production-quality B-rep kernels — NX on Siemens' own Parasolid kernel, Kerf on Open CASCADE Technology (OCCT). Both treat parametric feature modelling as the primary design workflow, with a constraint-based sketcher, feature tree history, and downstream fabrication awareness (flat patterns, drawings, tolerances). Both export STEP as the neutral interchange format.

Both tools acknowledge that mechanical design does not stop at geometry: NX bundles CAM, FEM simulation, and assembly analysis; Kerf bundles CAM, electronics, and a scripting API. The philosophies differ (NX is broad and deep; Kerf is broad and open), but the intent — a single tool that covers the engineering workflow from concept to output — is shared.

## Where Kerf wins

- **MIT open-core, no seat fee.** NX enterprise licensing runs to thousands of dollars per seat per year. Kerf is free locally and pay-as-you-go in the cloud. A startup or a student can run the full Kerf feature set without a purchase order.
- **Chat-native design.** Describe what you want in plain English; the LLM edits the feature-tree source backed by live doc-search. NX has no LLM interface. For iterative design exploration, Kerf's conversational workflow is dramatically faster than menu-driven parametric editing.
- **In-box electronics.** NX is a pure mechanical/CAM/simulation tool. Kerf ships PCB schematic, layout, pre-compliance simulation (SI/EMC/PDN/thermal), and full fab output (Gerber/IPC-2581/ODB++) — all without extension gating. Multi-domain products that include a PCB are first-class Kerf projects.
- **Open source / auditable.** The full Kerf codebase is MIT-licensed on GitHub. NX is proprietary and not auditable.
- **BYO LLM.** Bring your own Anthropic or OpenAI API key via the `kerf_byo` bucket; zero billing flows through Kerf. NX has no AI interface at all.

## Where NX wins

- **Synchronous technology.** NX's hybrid parametric/direct editing — where you can manipulate geometry without caring whether it was created with or without history — is a decade-long engineering investment with no peer. Kerf is feature-tree primary with limited direct editing.
- **Advanced surfacing (Class A).** NX Shape Studio and its curvature-continuity surface modelling tools (G2/G3 blending, reflection line analysis, sectional curvature combs) are automotive-grade. Kerf's NURBS Phase 4 is early.
- **Production CAM.** NX CAM's multi-axis machining, adaptive clearing, and verified toolpath simulation have been validated in production aerospace and automotive shops for decades. Kerf's CAM is younger.
- **Nastran-grade FEM.** NX's built-in Simcenter FEM, including pre/post-processing and solver integration, provides structural, thermal, fatigue, and vibration analysis at a depth Kerf does not approach.
- **PLM integration.** NX integrates natively with Teamcenter for BOM, change management, and programme-level configuration — enterprise-scale product lifecycle management that Kerf's cloud git layer does not target.

## Feature matrix

| Feature | Kerf | Siemens NX |
|---|---|---|
| License | MIT open-core | Proprietary enterprise (VAR) |
| Cost | Free local; hosted credits | Thousands USD/seat/yr |
| B-rep kernel | Open CASCADE (OCCT) | Parasolid |
| Parametric history | Feature DAG | History tree + Synchronous Technology |
| Direct editing | Limited | Synchronous Technology (mature) |
| Class-A surfacing | NURBS Phase 4 (early) | NX Shape Studio (automotive-grade) |
| Sheet metal | Flange + unfold + flat-pattern | Sheet Metal workbench (mature) |
| Assembly | Assembly mates | Full assembly + kinematic simulation |
| FEM / simulation | Not yet | Simcenter FEM (Nastran-grade) |
| CAM | 3-axis + 5-axis 3+2 | Multi-axis NX CAM (mature, production) |
| PCB / electronics | In-box (schematic + layout + SI/EMC/PDN) | Not included |
| Chat / LLM editing | Chat-native | None |
| Python scripting | kerf-sdk on PyPI | NX Open (C++/Python) |
| STEP export | Yes | Yes |
| Open source | Yes (MIT) | No |

## Both produce STEP

NX and Kerf both export ISO 10303 STEP (AP214 / AP242). STEP is the universal handshake between high-end mechanical CAD tools; geometry produced in NX can be imported into Kerf for downstream electronics integration, annotation, or scripting — and vice versa.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Siemens Digital Industries product pages. Kerf capabilities reflect the current shipped product.*
