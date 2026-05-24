---
slug: maxsurf
competitor: "Bentley Maxsurf"
category: cad-mechanical
left: kerf
right: maxsurf
hero_tagline: "Integrated naval architecture hull design and stability platform — versus an open-core CAD with hydrostatics, seakeeping, and resistance prediction."
reviewed_at: 2026-05-24
features:
  - domain: D5
    feature: "Hull form modelling (NURBS)"
    competitor:
      status: yes
      note: "3D NURB surface hull modelling; parametric hull form generation with interactive sketch tools"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: partial
      note: "NURBS surfacing math complete; OCCT bindings unconfirmed at build; no hull-specific parametric UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"
  - domain: D5
    feature: "Hydrostatics (intact)"
    competitor:
      status: yes
      note: "Full hydrostatic calculations: displacement, VCB, BM, GM, curves of form from 3D hull"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Hydrostatics: displacement, BM, GM, trim, freeboard (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/hydrostatics.py"
  - domain: D5
    feature: "Intact and damage stability (IMO)"
    competitor:
      status: yes
      note: "Intact + probabilistic damage stability; IMO IS-Code and SOLAS compliance checks"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Intact stability (GZ curve, IMO criteria) and damage stability (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/stability.py"
  - domain: D5
    feature: "Resistance prediction"
    competitor:
      status: yes
      note: "Holtrop-Mennen, Savitsky (planing), and other resistance prediction methods"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Holtrop-Mennen resistance prediction (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/holtrop_mennen.py"
  - domain: D5
    feature: "Seakeeping / motions"
    competitor:
      status: yes
      note: "Radiation diffraction panel method for motions prediction; ship response to waves"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Seakeeping: heave/pitch/roll RAOs + added mass + damping (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/seakeeping.py"
  - domain: D5
    feature: "Structural analysis (scantlings)"
    competitor:
      status: yes
      note: "Structural modelling and analysis; class-rule scantling checks; longitudinal strength"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: partial
      note: "Structural FEA backend (beam/plate); no class-rule marine scantling specific calculator. Full Lloyd's/DNV/BV/ABS rule implementation requires rule-tree encoding for each class society — significant scope; flagged for wave 2 (kerf-marine v2 + kerf-structural collaboration)."
      evidence: "packages/kerf-structural/src/"
  - domain: D5
    feature: "Sailing VPP"
    competitor:
      status: yes
      note: "Velocity prediction program for sailing vessels"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Full sailing VPP: ITTC 1957 friction + Delft-series residuary resistance; Dittus empirical sail polar (CL/CD vs AWA) for main+jib; apparent-wind calculation; equilibrium solver (drive=resistance, heel balance); polar generation across TWS/TWA sweep; VMG optimisation"
      evidence: "packages/kerf-marine/src/kerf_marine/vpp.py"
  - domain: D5
    feature: "Section / body-plan curves"
    competitor:
      status: yes
      note: "Automatic section generation and body plan from 3D hull model"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Hull section curve extraction (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/sections.py"
  - domain: D1
    feature: "DXF / IGES / 3DM file exchange"
    competitor:
      status: yes
      note: "DGN, 3DM (Rhino), IGES, DXF interchange; integrates with MicroStation, Rhino, AutoCAD"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: partial
      note: "STEP export; limited IGES; no DGN/3DM exchange"
      evidence: "packages/kerf-imports/src/"
  - domain: D1
    feature: "LLM / chat-native editing"
    competitor:
      status: no
      note: "No LLM interface in Maxsurf as of May 2026"
      source: "https://www.bentley.com/software/maxsurf/"
    kerf:
      status: yes
      note: "Chat-native: describe vessel parameters; Kerf runs hydrostatics and stability"
      evidence: "src/components/ChatPanel.jsx"
---

# Kerf vs Bentley Maxsurf

Maxsurf (now part of Bentley Systems) is the integrated naval architecture suite trusted by ship designers and yards worldwide for hull modelling, hydrostatics, stability, resistance prediction, seakeeping, and structural analysis. It operates from a single parametric 3D NURBS hull model that feeds all downstream analyses — intact and damage stability to IMO criteria, Holtrop-Mennen resistance, radiation-diffraction seakeeping, and longitudinal strength. Maxsurf is cross-discipline for the maritime domain. Kerf approaches naval architecture as an engineering engine: hydrostatics, stability, seakeeping, resistance prediction, and structural FEA — all from a Python API or chat prompt — but without Maxsurf's parametric hull modelling UI.

## Where Maxsurf is strong

- **Parametric hull form modelling.** Maxsurf's NURBS surface modeller with hull form wizards and interactive sketch tools is purpose-built for hull design — with automatic section generation, body plans, and fairness analysis. Kerf has NURBS mathematics but no hull-specific parametric modelling UI.
- **Single model → all analyses.** Changes to the hull form propagate immediately to hydrostatics, stability curves, resistance, and seakeeping — all from one parametric 3D model. Kerf's engines are wired separately.
- **Damage stability (probabilistic).** Full probabilistic damage stability to IMO SOLAS requirements — a regulatory requirement for most commercial vessels. Kerf's damage stability is simpler.
- **Sailing VPP.** Maxsurf includes an integrated velocity prediction programme for sailing vessels. Kerf has no sailing VPP.
- **Class-rule scantlings.** Longitudinal strength and structural analysis with class society rule checks. Kerf has general structural FEA but no marine class-rule scantling calculator.
- **CAD interoperability.** Maxsurf reads and writes 3DM (Rhino), DGN (MicroStation), IGES, and DXF — the formats of the naval architecture supply chain. Kerf supports STEP and limited IGES.

## Where Kerf differs

- **MIT open-core.** Maxsurf is proprietary, subscription-priced (Bentley licensing). Kerf is MIT-licensed — free locally.
- **Sailing VPP.** Kerf includes a full velocity prediction programme: ITTC 1957 frictional resistance, Delft-series residuary resistance, empirical sail polar (CL/CD vs AWA for main+jib), apparent-wind model, equilibrium solver, and polar generation across TWS/TWA sweeps with VMG optimisation.
- **Multi-domain workspace.** Combine Kerf's marine engineering with structural FEA, thermal analysis, composites, and electronics in one project — typical for fast patrol vessels, autonomous surface vehicles, and naval platforms. Maxsurf is maritime-only.
- **Chat-native.** Describe vessel parameters in plain language; Kerf runs hydrostatics and stability. Maxsurf has no LLM interface.
- **Python scripting.** kerf-sdk on PyPI for automated hull analysis workflows. Maxsurf scripting is limited.

## Honest gaps — where Kerf is behind today

- **No parametric hull form modeller.** The core of Maxsurf — NURBS hull modelling with fairness and section generation — is absent in Kerf.
- **No marine class-rule scantlings.** No Lloyd's, DNV, Bureau Veritas, or ABS rule-check for structural scantlings. Full class-rule encoding is a large scope item requiring kerf-marine v2 + kerf-structural collaboration.
- **Damage stability depth.** Maxsurf's probabilistic damage stability is more comprehensive than Kerf's implementation.
- **No marine UI.** Kerf's entire marine engineering capability is backend/LLM-tool; there is no interactive naval architecture panel in the browser.

## Side by side

| Feature | Kerf | Bentley Maxsurf |
|---|---|---|
| License | MIT open-core | Proprietary (Bentley subscription) |
| Primary focus | Multi-domain engineering CAD | Naval architecture |
| Hull form modelling (NURBS) | Partial (no hull UI) | Yes (purpose-built) |
| Hydrostatics | Yes (backend) | Yes |
| Intact + damage stability | Yes (backend) | Yes (IMO SOLAS probabilistic) |
| Resistance prediction | Yes (Holtrop-Mennen, backend) | Yes |
| Seakeeping / RAOs | Yes (backend) | Yes (radiation diffraction) |
| Sailing VPP | Yes (ITTC+Delft+sail polar, backend) | Yes |
| Structural / scantlings | General FEA (backend) | Class-rule specific |
| Marine UI | None (backend only) | Full integrated GUI |
| Chat / LLM editing | Chat-native | None |
| Open source | Yes (MIT) | No |

---
*Last reviewed: 2026-05-24. Competitor information sourced from Bentley Maxsurf product pages. Kerf capabilities reflect the current shipped product.*
