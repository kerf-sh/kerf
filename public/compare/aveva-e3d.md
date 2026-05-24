---
slug: aveva-e3d
competitor: "AVEVA E3D Design"
category: cad-mechanical
left: kerf
right: aveva-e3d
hero_tagline: "The enterprise piping and plant design platform — versus an open-core CAD with P&ID, isometric generation, and piping stress in one workspace."
reviewed_at: 2026-05-24
features:
  - domain: D13
    feature: "Piping route design (3D intelligent)"
    competitor:
      status: yes
      note: "Rule-driven 3D piping routing; pipe class/material/spec enforcement; automatic clash detection"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: partial
      note: "Piping isometric/P&ID backend engine; no interactive 3D piping routing UI"
      evidence: "packages/kerf-piping/src/kerf_piping/isometric.py"
  - domain: D13
    feature: "Piping component catalogue"
    competitor:
      status: yes
      note: "Centralised catalogue of elbows, tees, valves, reducers, flanges with spec-driven selection"
      source: "https://www.multisoftsystems.com/article/aveva-e3d-piping-the-future-of-intelligent-3d-plant-design"
    kerf:
      status: partial
      note: "Piping symbols and P&ID component library (backend); no 3D component catalogue"
      evidence: "packages/kerf-piping/src/kerf_piping/symbols.py"
  - domain: D13
    feature: "Isometric drawing generation"
    competitor:
      status: yes
      note: "Fabrication-ready isometric drawings with BOM, weld details, spool numbers, dimensions — auto-generated from 3D model"
      source: "https://www.multisoftsystems.com/article/aveva-e3d-piping-the-future-of-intelligent-3d-plant-design"
    kerf:
      status: yes
      note: "Isometric drawing generation from P&ID data (backend)"
      evidence: "packages/kerf-piping/src/kerf_piping/isometric.py"
  - domain: D13
    feature: "P&ID integration / data synchronisation"
    competitor:
      status: yes
      note: "Seamless integration with AVEVA Engineering and AVEVA P&ID; upstream changes propagate to 3D model"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: yes
      note: "P&ID authoring with PID symbols; backend engine wired"
      evidence: "packages/kerf-piping/src/kerf_piping/pid.py"
  - domain: D13
    feature: "Clash detection (hard/soft)"
    competitor:
      status: yes
      note: "Hard, soft, and touch clash classifications; real-time highlighting; laser scan integration"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: partial
      note: "Clash detection in assembly (OBB-SAT + BVH backend); no P&ID/plant-specific clash UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/clash/detect.py"
  - domain: D13
    feature: "Multi-discipline plant design (structural/HVAC/civil)"
    competitor:
      status: yes
      note: "Structural, civil, HVAC, cable tray, equipment — all disciplines in one AVEVA E3D model"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: partial
      note: "Structural FEA, HVAC sizing, civil — separate packages but not a unified plant model"
      evidence: "packages/kerf-structural/"
  - domain: D13
    feature: "Global multi-user concurrent design"
    competitor:
      status: yes
      note: "AVEVA Global technology: multiple users across locations work simultaneously; real-time sync"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: partial
      note: "Cloud git workspace with branch/merge; not real-time concurrent design at plant-model scale"
      evidence: "cloud/git/"
  - domain: D13
    feature: "Laser scan / point cloud integration"
    competitor:
      status: yes
      note: "Point cloud import from any laser scanner; brownfield retrofit design against as-built geometry"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: no
      note: "No point cloud / laser scan integration"
      evidence: ""
  - domain: D4
    feature: "HVAC duct sizing"
    competitor:
      status: yes
      note: "HVAC/ductwork routing discipline within E3D Design plant model"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: yes
      note: "SMACNA duct sizing + flat-pattern (backend)"
      evidence: "packages/kerf-hvac/src/"
  - domain: D2
    feature: "Piping stress / structural FEA"
    competitor:
      status: partial
      note: "E3D integrates with AVEVA Mechanical Analyser and third-party tools (Caesar II) for piping stress; not native"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: yes
      note: "Full structural FEA: 1D beam, ASME VIII pressure vessels, API 650 tanks (backend)"
      evidence: "packages/kerf-structural/src/"
  - domain: D1
    feature: "LLM / industrial AI assistant"
    competitor:
      status: partial
      note: "AVEVA E3D includes in-built AI tools and an LLM industrial assistant (as of 2026)"
      source: "https://www.aveva.com/en/products/e3d-design/"
    kerf:
      status: yes
      note: "Chat-native: plain-language design edits; full LLM tool routing for all backend engines"
      evidence: "src/components/ChatPanel.jsx"
---

# Kerf vs AVEVA E3D Design

AVEVA E3D Design (formerly PDMS) is the dominant enterprise 3D plant design platform for process plants, marine vessels, and power infrastructure. It integrates piping, structural, civil, HVAC, and cable tray design across global multi-user teams — with rule-driven routing, real-time clash detection, automatic isometric drawing generation, and P&ID-to-3D synchronisation. AVEVA is part of Schneider Electric. Pricing is enterprise-bespoke (not publicly listed) and deployment is typically on-premise or via AVEVA Connect cloud. Kerf provides the piping and plant engineering calculations — P&ID authoring, isometric generation, HVAC sizing, structural FEA — in an MIT-licensed workspace, but without the 3D plant routing and multi-discipline coordination depth of E3D.

## Where AVEVA E3D is strong

- **3D intelligent piping routing.** AVEVA E3D's rule-driven 3D routing enforces pipe class, material, specification, and code compliance as the engineer routes. Clash detection is hard-wired into the workflow. Kerf has no equivalent 3D routing UI.
- **Multi-discipline coordination.** Every discipline — piping, structural steel, civil, HVAC, cable tray, equipment — works in the same model with cross-discipline clash detection. Kerf's disciplines exist in separate packages.
- **Isometric and orthographic drawing automation.** AVEVA E3D generates fabrication-ready isometrics (with spool numbers, weld marks, BOM) directly from the 3D model. Kerf generates isometrics from P&ID data, not from a 3D routing model.
- **Global concurrent design.** AVEVA Global technology lets teams in different countries work on the same project simultaneously with real-time synchronisation. Kerf's collaboration is git-based (branch/merge), not real-time concurrent.
- **Laser scan integration.** Point cloud import for brownfield retrofit — model against as-built geometry. Kerf has no point cloud capability.
- **Asset lifecycle / digital twin.** AVEVA E3D is designed for the full asset lifecycle from FEED through commissioning and handover into operations. Kerf is a design tool, not an asset management platform.

## Where Kerf differs

- **MIT open-core.** AVEVA E3D is enterprise-priced (multi-year site licences, not publicly listed). Kerf is MIT-licensed — free locally.
- **Structural + piping stress.** AVEVA E3D relies on third-party tools (Caesar II) for piping stress analysis. Kerf includes ASME VIII pressure vessel design, API 650 tank design, and full structural FEA natively.
- **HVAC engineering calculations.** Kerf's HVAC engine performs SMACNA duct sizing and generates flat patterns. E3D routes HVAC ducts in 3D but does not do sizing calculations.
- **Chat-native.** Kerf's LLM interface enables plain-language piping edits and P&ID generation. AVEVA E3D has added LLM-based assistance in 2026, but it is assistive rather than generative.
- **Python scripting.** kerf-sdk on PyPI; no proprietary scripting environment required.

## Honest gaps — where Kerf is behind today

- **No 3D piping routing UI.** This is the core feature of E3D. Kerf has P&ID and isometric generation (backend) but no 3D intelligent routing in the browser.
- **No multi-discipline plant model.** E3D's unified plant model with cross-discipline clash detection is the industry standard for large projects. Kerf's disciplines are separate.
- **No laser scan / brownfield support.** Critical for retrofit and brownfield engineering.
- **No enterprise project management.** Deliverable management, approvals, mark-ups, versioning for EPC projects — none of this is in Kerf.

## Side by side

| Feature | Kerf | AVEVA E3D Design |
|---|---|---|
| License | MIT open-core | Enterprise (bespoke pricing) |
| Primary focus | Multi-domain engineering CAD | 3D plant / piping design |
| 3D piping routing | No | Yes (rule-driven, spec-compliant) |
| P&ID authoring | Yes (backend) | Via AVEVA P&ID integration |
| Isometric drawing generation | Yes (from P&ID, backend) | Yes (from 3D model, automated) |
| Clash detection | Backend only | Yes (hard/soft/touch, real-time) |
| Piping stress analysis | ASME VIII + API 650 native | Via Caesar II (third-party) |
| Multi-discipline plant model | Separate packages | Unified plant model |
| Laser scan integration | No | Yes |
| Global concurrent design | Git branch/merge | Yes (AVEVA Global, real-time) |
| Chat / LLM | Chat-native | LLM assistant (2026) |
| Open source | Yes (MIT) | No |

---
*Last reviewed: 2026-05-24. Competitor information sourced from public AVEVA E3D Design product pages and technical articles. Kerf capabilities reflect the current shipped product.*
