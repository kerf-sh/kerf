---
slug: fibersim
competitor: "Siemens Fibersim"
category: cad-mechanical
left: kerf
right: fibersim
hero_tagline: "The composites ply design and manufacturing tool — versus an open-core CAD with CLT, failure analysis, AFP/ATL output, and multi-domain engineering."
reviewed_at: 2026-05-24
features:
  - domain: D13
    feature: "Ply-based laminate layup design"
    competitor:
      status: yes
      note: "Ply-based and zone-based design; automated ply table generation; splice and dart management"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Layup definition with ply angles, materials, and stacking sequences (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/layup.py"
  - domain: D13
    feature: "Drape simulation / producibility"
    competitor:
      status: yes
      note: "Producibility simulation: accurate flat patterns and true fiber orientations; real-time darting feedback"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Drape simulation for composite prepreg on doubly-curved surfaces (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/drape.py"
  - domain: D13
    feature: "AFP / ATL manufacturing path output"
    competitor:
      status: yes
      note: "Automated Fiber Placement (AFP) and Automated Tape Laying (ATL) path export for CNC path planners"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: no
      note: "No AFP/ATL CNC path generation"
      evidence: ""
  - domain: D2
    feature: "Classical laminate theory (CLT)"
    competitor:
      status: yes
      note: "Bi-directional CAE interface; CLT via Simcenter integration; stiffness/strength in FEA"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "CLT: [A][B][D] stiffness matrices, coupling analysis (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/clt.py"
  - domain: D2
    feature: "Composite failure analysis"
    competitor:
      status: partial
      note: "Failure via Simcenter FEA integration; Fibersim does not solve failure criteria natively"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Tsai-Wu, Tsai-Hill, max-stress, max-strain, Hashin, Puck failure criteria (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/failure.py"
  - domain: D2
    feature: "Interlaminar shear and delamination"
    competitor:
      status: partial
      note: "Core sampling shows ply thickness and fiber deviation; interlaminar stress via FEA tools"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Interlaminar shear stress with ILSS failure index; progressive delamination (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/interlaminar.py"
  - domain: D2
    feature: "Thermal residual stress"
    competitor:
      status: partial
      note: "Thermal effects via Simcenter FEA; not native in Fibersim design tool"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Thermal residual stress from cure temperature delta (backend)"
      evidence: "packages/kerf-composites/src/kerf_composites/thermal_residual.py"
  - domain: D13
    feature: "Multi-CAD support (NX / CATIA / Creo)"
    competitor:
      status: yes
      note: "Multi-CAD: Fibersim runs inside NX, CATIA V5/V6, and Creo as native plug-in"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Standalone open-core CAD; no plug-in for NX/CATIA/Creo (is its own CAD)"
      evidence: "packages/kerf-cad-core/src/"
  - domain: D13
    feature: "Laser projection / flat pattern export"
    competitor:
      status: yes
      note: "Flat pattern export for laser projector and ply cutting; accurate net shape patterns"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: no
      note: "No laser projection output or flat ply pattern for hand layup"
      evidence: ""
  - domain: D14
    feature: "Laminate weight / cost"
    competitor:
      status: yes
      note: "Instant laminate weight and cost including post-cure processes during review"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: partial
      note: "LCA material costing; no composites-specific laminate weight/cost UI"
      evidence: "packages/kerf-lca/phases.py"
  - domain: D1
    feature: "LLM / chat-native editing"
    competitor:
      status: no
      note: "No LLM interface in Fibersim as of May 2026"
      source: "https://www.siemens.com/en-us/products/designcenter/nx-cad-software/offerings/fibersim-composites/"
    kerf:
      status: yes
      note: "Chat-native: describe layup in plain language; Kerf routes to composites backend"
      evidence: "src/components/ChatPanel.jsx"
---

# Kerf vs Siemens Fibersim

Siemens Fibersim is the industry-standard ply design and manufacturing tool for advanced composite structures — used in aerospace, automotive, wind energy, and sporting goods. It runs as a native plug-in inside NX, CATIA, and Creo, connecting composite design directly to the host CAD model. Its key strengths are ply-based and zone-based layup design, producibility simulation that predicts fiber orientations on doubly-curved surfaces, AFP/ATL path export for automated manufacturing, and a bi-directional CAE interface to Simcenter FEA. Kerf approaches composites from the analysis side: CLT stiffness matrices, six failure criteria, interlaminar shear, thermal residual stress — all in the same open-core workspace alongside structural FEA, thermal analysis, and mechanical CAD.

## Where Fibersim is strong

- **Ply design and manufacturing integration.** Fibersim's ply-based authoring, splice and dart management, and AFP/ATL path export are specifically designed to drive automated manufacturing equipment. Kerf has no AFP/ATL output.
- **Producibility simulation.** Fibersim simulates whether a ply can be physically laid on a doubly-curved surface — predicting fiber wrinkling and yarn distortion before any material is cut. Kerf's drape simulation is an engineering calculation, not a manufacturing producibility predictor.
- **Flat pattern / laser projection.** Fibersim generates accurate flat patterns for hand layup and laser projector systems. Kerf has no laser projector output.
- **NX / CATIA / Creo integration.** For organisations already using Siemens NX or Dassault CATIA, Fibersim integrates directly — the composite design lives alongside the master CAD model. Kerf is its own CAD environment.
- **Plybook documentation.** Automated plybook and ply table generation with cross-sections, annotations, and core sampling — the standard manufacturing document for composite fabrication. Kerf has no plybook.
- **Laminate weight + cost.** Instant laminate weight and cost including post-cure processes during design review. Kerf has no composites-specific costing.

## Where Kerf differs

- **MIT open-core.** Fibersim is part of Siemens' NX suite — priced at enterprise NX licence levels. Kerf is MIT-licensed — free locally.
- **Failure analysis native.** Kerf runs Tsai-Wu, Tsai-Hill, max-stress, max-strain, Hashin, and Puck failure criteria natively in the composites engine. Fibersim defers failure analysis to Simcenter FEA.
- **Interlaminar shear and delamination.** Kerf calculates interlaminar shear stress with ILSS failure index and progressive delamination natively. Fibersim does this via FEA integration.
- **Thermal residual stress.** Kerf calculates cure-induced thermal residual stresses from laminate thermal properties and cure temperature delta. Fibersim routes this to FEA.
- **Multi-domain workspace.** A composites engineer can combine Kerf's CLT + failure analysis with structural FEA, LCA, and manufacturing simulation in one project. Fibersim is composites-only.
- **Chat-native.** Describe a layup sequence in plain language; Kerf calculates [A][B][D] matrices and failure margins. Fibersim has no LLM interface.

## Honest gaps — where Kerf is behind today

- **No AFP/ATL manufacturing output.** Critical for automated fibre placement; Kerf cannot drive AFP/ATL machines.
- **No flat pattern / laser projection.** Cannot generate ply flat patterns or drive a laser projector for hand layup.
- **No plybook.** No automated manufacturing documentation for composite fabrication.
- **No CAD plug-in model.** Fibersim's value is partly in living inside the master CAD model (NX/CATIA/Creo) — Kerf is standalone.
- **Producibility simulation depth.** Fibersim's drape and producibility simulation is more mature than Kerf's analytical drape model.

## Side by side

| Feature | Kerf | Siemens Fibersim |
|---|---|---|
| License | MIT open-core | Part of Siemens NX (enterprise) |
| Primary focus | Multi-domain engineering CAD | Composites ply design + manufacturing |
| Layup definition | Yes (backend) | Yes |
| Drape simulation | Yes (backend) | Yes (producibility) |
| AFP / ATL path output | No | Yes |
| CLT [A][B][D] matrices | Yes (backend) | Via Simcenter FEA |
| Failure criteria (6) | Yes (backend) | Via Simcenter FEA |
| Interlaminar shear | Yes (backend) | Via FEA |
| Thermal residual stress | Yes (backend) | Via FEA |
| Flat pattern / laser proj. | No | Yes |
| Plybook documentation | No | Yes |
| NX / CATIA / Creo plug-in | No (standalone) | Yes (native) |
| Chat / LLM editing | Chat-native | None |
| Open source | Yes (MIT) | No |

---
*Last reviewed: 2026-05-24. Competitor information sourced from Siemens Fibersim product pages. Kerf capabilities reflect the current shipped product.*
