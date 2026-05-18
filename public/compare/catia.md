---
slug: catia
competitor: Dassault CATIA
category: cad-mechanical
left: kerf
right: catia
hero_tagline: "CATIA built the A380 — Kerf builds the next generation of engineers who work without seat fees."
---

# Kerf vs Dassault CATIA

Dassault CATIA is the gold standard for complex-surface and multi-disciplinary product engineering in automotive and aerospace. Airbus, Boeing, and every major car OEM use CATIA V5 or 3DEXPERIENCE to define their master geometry. It is extraordinarily capable and extraordinarily expensive — six-figure enterprise licensing is common. Kerf is the MIT-licensed, chat-native alternative for the next generation of engineers who cannot or should not pay that freight.

## Where they converge

Both CATIA and Kerf start from a parametric B-rep kernel and a constraint-based sketcher. Both emphasise geometric precision over approximate mesh-based workflows — tolerances matter, and both tools treat the model as the source of truth for downstream fabrication. Both support STEP as the neutral exchange format, which means geometry moves between them without reconstruction.

Both tools also reach across disciplines: CATIA's 3DEXPERIENCE platform wraps mechanical, electrical, simulation, and PLM in one umbrella; Kerf similarly covers parametric mechanical, sheet metal, drawings, PCB electronics, and scripting in a single environment. The philosophy of "one workspace, not a collection of siloed applications" is shared.

Finally, both acknowledge that assembly is central to real engineering. CATIA's product structure with constraints and tolerance analysis, and Kerf's assembly mates, address the same fundamental need: expressing how parts relate, not just how individual parts are shaped.

## Where Kerf wins

- **MIT open-core, zero seat fee.** CATIA licensing starts in the thousands of dollars per seat per year and often requires VAR negotiation. Kerf is free locally under MIT — the full feature set runs on a laptop with a single binary install. Teams that cannot justify enterprise CAD spend can do real engineering work with Kerf immediately.
- **Chat-native workflow.** Describe a design intent — "add a 3mm fillet to all concave edges" or "change the flange material to aluminium 6061 and recalculate the flat pattern" — and Kerf's LLM edits the feature tree directly, backed by doc-search so it does not invent surface. CATIA has no comparable natural-language interface.
- **BYO LLM / BYO key.** Bring your own Anthropic or OpenAI API key; zero billing flows through Kerf in the `kerf_byo` tier. CATIA has no configurable LLM at all.
- **In-box electronics.** CATIA is a pure mechanical tool at its core — PCB schematic, layout, pre-compliance simulation (SI/EMC/PDN/thermal), and fab output are not part of its base offering. Kerf ships all of these without extension gating.
- **Single-binary offline install.** A brew or curl install produces a fully functional offline binary. CATIA requires Windows, a licence server, and a complex installer suite that takes hours. Kerf runs on macOS, Windows, and Linux.

## Where CATIA wins

- **Class-A surface quality.** CATIA's FreeStyle and ICEM Surf workspaces, with their curvature-continuity tools (G2/G3 surface blends, highlight analysis, isophote visualisation), are the industry benchmark for automotive exterior surfacing. Kerf's NURBS Phase 4 is early and does not approach this.
- **Kinematics and DMU.** CATIA's Digital Mock-Up (DMU) Kinematics workbench models complex mechanical linkages, cam followers, and multi-body motion with interference sweeps and envelope computation. Kerf has no kinematic simulation.
- **Multi-physics CAE.** CATIA Simulation, together with SIMULIA Abaqus, provides structural, thermal, fatigue, and crash-analysis workflows that Kerf does not touch. For full-vehicle FEA sign-off, CATIA's ecosystem is irreplaceable.
- **PLM and configuration management.** ENOVIA / 3DEXPERIENCE offers programme-level BOM management, change orders, effectivity, and configuration at a scale that Kerf's cloud git collaboration layer does not target.
- **Industry certification and validation.** Airframe geometry derived in CATIA carries a paper trail from master model to CNC to inspection report that regulatory bodies accept. Kerf has no certification pathway today.

## Feature matrix

| Feature | Kerf | CATIA (3DEXPERIENCE / V5) |
|---|---|---|
| License | MIT open-core | Proprietary enterprise (VAR, six-figure) |
| Cost | Free local; pay-as-you-go hosted credits | Thousands USD/seat/yr |
| Offline / self-host | Full offline single binary | Windows + licence server required |
| Parametric B-rep | OCCT feature tree | CATIA V5 / CGM kernel |
| Constraint sketcher | Sketcher v2 | CATIA Sketcher (mature) |
| Class-A surfacing | NURBS Phase 4 (early) | FreeStyle / ICEM Surf (industry gold standard) |
| Sheet metal | Flange + unfold + flat-pattern DXF | Sheet Metal workbench (mature) |
| Assembly | Assembly mates | Product Structure + Kinematics (mature) |
| Kinematic simulation | Not yet | DMU Kinematics (mature) |
| FEM / structural CAE | Not yet | SIMULIA / CATIA Simulation (deep) |
| PCB / electronics | In-box schematic + layout + pre-compliance | Not included (separate tools) |
| Chat / LLM editing | Chat-native | None |
| Python scripting | kerf-sdk on PyPI | CAA RADE (C++) |
| STEP export | Yes | Yes |
| BIM / IFC | IFC Tier 2 import | Limited |
| Open source | Yes (MIT) | No |

## Both produce STEP

CATIA and Kerf both export ISO 10303 STEP (AP214 / AP242). STEP is the universal handshake between CAD systems, and the fact that both tools produce it means geometry flows cleanly — take a CATIA surface, import it into Kerf for downstream electronics integration or drawing annotation, and move on.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Dassault Systèmes pricing and product pages. Kerf capabilities reflect the current shipped product.*
