---
slug: max3ds
competitor: "Autodesk 3ds Max"
category: dcc
left: kerf
right: max3ds
hero_tagline: "Archviz & game-art DCC — a different category from B-rep CAD."
reviewed_at: 2026-05-19
order: 2
features:
  - domain: D1
    feature: "Geometry — B-rep solid kernel"
    competitor:
      status: no
      note: "3ds Max is mesh-first (Edit Poly); no B-rep boundary representation"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "OCCT B-rep kernel — exact rational geometry"
      evidence: "packages/kerf-occt/"
  - domain: D1
    feature: "Geometry — constraint sketcher"
    competitor:
      status: no
      note: "3ds Max has no 2D constraint sketcher; splines are freeform"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "PlaneGCS WASM sketcher v2 — geometric + dimensional constraints"
      evidence: "src/components/Sketcher/"
  - domain: D1
    feature: "Geometry — parametric feature history DAG"
    competitor:
      status: partial
      note: "Linear Modifier Stack per object; not a persistent face-ID DAG"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "OCCT feature tree with persistent face IDs"
      evidence: "packages/kerf-occt/"
  - domain: D1
    feature: "Geometry — STEP / IGES B-rep interop"
    competitor:
      status: partial
      note: "STEP import via plugin only; no B-rep STEP writer; primary format is FBX/DWG"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "STEP / IGES / 3DM B-rep round-trip"
      evidence: "packages/kerf-occt/io/"
  - domain: D1
    feature: "Geometry — polygon mesh modelling"
    competitor:
      status: yes
      note: "Industry-standard Edit Poly + 35-year Modifier Stack (TurboSmooth, Chamfer, Bend, etc.)"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: partial
      note: "SubD authoring + poke/extrude/subdivide/sculpt + quad/isotropic remesh; no Modifier Stack depth"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/subd_tools.py"
  - domain: D2
    feature: "Structural / FEA — code checks (AISC, ACI, ASCE 7)"
    competitor:
      status: no
      note: "3ds Max is a DCC, not a structural analysis tool; no engineering code checks"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "AISC 360-22, ACI 318-19, ASCE 7-22 seismic/wind (backend)"
      evidence: "packages/kerf-structural/"
  - domain: D2
    feature: "Structural / FEA — finite element analysis"
    competitor:
      status: no
      note: "3ds Max has no FEA solver; cloth/fluid sims are visual not structural"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Native beam/MITC4 plate FEM + CalculiX bridge (backend)"
      evidence: "packages/kerf-fem/"
  - domain: D3
    feature: "Machine elements — gear, bearing, fastener rating"
    competitor:
      status: no
      note: "3ds Max is rendering/animation, not machine-element engineering"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "AGMA 2001-D04 / ISO 6336 gears, ISO 281 bearings, VDI 2230 fasteners (backend)"
      evidence: "packages/kerf-mechanical/"
  - domain: D4
    feature: "Thermal / fluid / HVAC — heat-exchanger and pipe-network calc"
    competitor:
      status: no
      note: "3ds Max has no thermal or fluid engineering calculations"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "LMTD + Bell-Delaware shell-and-tube, Hardy-Cross pipe network (backend)"
      evidence: "packages/kerf-thermal/"
  - domain: D4
    feature: "Thermal / fluid — visual fluid simulation (Phoenix FD)"
    competitor:
      status: yes
      note: "Phoenix FD plugin: GPU-accelerated fire, smoke, liquid for VFX/archviz"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: no
      note: "No visual fluid VFX simulation"
      evidence: ""
  - domain: D5
    feature: "Aero / marine / space — aerodynamic and orbital analysis"
    competitor:
      status: no
      note: "3ds Max is a DCC; no aerodynamic or space-mission analysis"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "VLM, XFOIL-class airfoil, orbital mechanics, Lambert solver (backend)"
      evidence: "packages/kerf-aero/"
  - domain: D6
    feature: "Electronics / EDA — schematic, PCB, DRC"
    competitor:
      status: no
      note: "3ds Max has no EDA capability; not applicable to electronics design"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Full EDA: schematic capture, PCB layout, DRC, Gerber/IPC-2581"
      evidence: "packages/kerf-ecad/"
  - domain: D6
    feature: "Electronics — SPICE simulation"
    competitor:
      status: no
      note: "3ds Max has no circuit simulation capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Real ngspice bridge wired"
      evidence: "packages/kerf-spice/"
  - domain: D7
    feature: "Manufacturing / CAM — CNC toolpath generation"
    competitor:
      status: no
      note: "3ds Max has no CAM capability; no G-code output"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "3-axis CAM (profile/pocket/contour) via opencamlib; G-code post (Fanuc/GRBL)"
      evidence: "packages/kerf-cam/"
  - domain: D7
    feature: "Manufacturing — FDM slicing"
    competitor:
      status: no
      note: "3ds Max has no 3D-print slicing; STL export only"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Cura slicing wired (PrintSliceView)"
      evidence: "src/components/PrintSliceView/"
  - domain: D8
    feature: "Civil / infrastructure — road alignment, pavement, geotech"
    competitor:
      status: no
      note: "3ds Max has no civil engineering analysis capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "AASHTO alignment, pavement AASHTO '93, geotech liquefaction (backend)"
      evidence: "packages/kerf-civil/"
  - domain: D9
    feature: "Dynamics / controls — rigid-body and controls simulation"
    competitor:
      status: partial
      note: "MassFX rigid-body and cloth are VFX sims, not engineering dynamics; no controls"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Lagrangian MBD, PID/LQR/Kalman state-space, 6-DOF IK (backend)"
      evidence: "packages/kerf-dynamics/"
  - domain: D9
    feature: "Dynamics — skeletal animation and rigging"
    competitor:
      status: yes
      note: "Full skeletal animation: IK/FK, CAT rig, Biped, morph targets, NLA"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: no
      note: "No skeletal animation or character rigging"
      evidence: ""
  - domain: D10
    feature: "Electrical / energy — power distribution and PLC"
    competitor:
      status: no
      note: "3ds Max has no electrical engineering, power, or PLC capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "NEC power distribution, AC load-flow, IEC 61131-3 PLC (ST + live Ladder)"
      evidence: "packages/kerf-electrical/"
  - domain: D11
    feature: "Tolerancing / QA — GD&T and tolerance stackup"
    competitor:
      status: no
      note: "3ds Max has no GD&T, tolerance, or metrology capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "ASME Y14.5 GD&T data model, 1D/3D tolerance stackup, SPC charts (backend)"
      evidence: "packages/kerf-tolerancing/"
  - domain: D12
    feature: "Optics — paraxial ABCD ray transfer"
    competitor:
      status: no
      note: "3ds Max is rendering/animation, not optics engineering"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Paraxial ABCD, Seidel aberrations, Gaussian beam propagation (backend)"
      evidence: "packages/kerf-optics/"
  - domain: D12
    feature: "Optics — production path-traced rendering (Arnold)"
    competitor:
      status: yes
      note: "Arnold GPU/CPU path tracer built-in; V-Ray, Corona, Redshift via plugins"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: partial
      note: "heroShot renderer (HDRI + ACES + bloom); no production path tracer"
      evidence: "src/components/HeroShot/"
  - domain: D12
    feature: "Acoustics — room acoustics and ISO 9613"
    competitor:
      status: no
      note: "3ds Max has no acoustic simulation capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "ISO 9613 propagation, RT60, image-source room IR, SEA (backend)"
      evidence: "packages/kerf-acoustics/"
  - domain: D13
    feature: "Verticals — jewelry design"
    competitor:
      status: partial
      note: "Possible via poly modelling; no parametric ring/stone/setting configurators"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "41-module jewelry suite: ring v4, gemstones v2, settings v3/v4, chain v2"
      evidence: "src/components/jewelry/"
  - domain: D13
    feature: "Verticals — BIM / architectural (IFC)"
    competitor:
      status: partial
      note: "Archviz-grade architectural modelling; no native IFC export or BIM data model"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Revit-comparable BIM engine: walls/slabs/framing/stairs + IFC4 export"
      evidence: "packages/kerf-bim/"
  - domain: D13
    feature: "Verticals — archviz creative workflow"
    competitor:
      status: yes
      note: "Purpose-built archviz: Chaos Cosmos assets, Forest Pack, RailClone, material libraries"
      source: "https://www.autodesk.com/products/3ds-max/"
    kerf:
      status: no
      note: "No archviz asset libraries or procedural scatter/population tools"
      evidence: ""
  - domain: D14
    feature: "Cost / materials — should-cost and LCA"
    competitor:
      status: no
      note: "3ds Max has no cost-estimation or lifecycle-assessment capability"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "Should-cost (Boothroyd-Dewhurst 6 processes), full ISO 14040/44 LCA (backend)"
      evidence: "packages/kerf-lca/"
  - domain: D14
    feature: "Cost / materials — material selection (Ashby)"
    competitor:
      status: no
      note: "3ds Max materials are rendering materials only; no engineering material selection"
      source: "https://help.autodesk.com/view/3DSMAX/2025/ENU/"
    kerf:
      status: yes
      note: "200-material Ashby selector (14 families) + Pareto frontier (backend)"
      evidence: "packages/kerf-matsel/"
---

# Kerf vs Autodesk 3ds Max

3ds Max is the industry-standard DCC tool for architectural visualisation, game art, and VFX: mature poly modeling, a rich modifier stack, built-in Arnold rendering, and an unmatched plugin ecosystem (V-Ray, Corona, Forest Pack). It is not a B-rep parametric CAD application. If you are evaluating 3ds Max for product engineering, jewelry production, or electronics design work — or considering it alongside Kerf for a visualisation pipeline — this page lays out where the two tools overlap, where they diverge, and which belongs in your workflow.

**These are different categories of tool.** Kerf is a B-rep parametric CAD environment with multi-discipline scope (mechanical, electronics, jewelry, architecture). 3ds Max is a mesh-first DCC and production rendering platform. The overlap is real — jewelry hero rendering, archviz, and product visualisation — but the primary jobs are different.

## Where 3ds Max is strong

- **Arnold built-in path tracer.** Arnold (GPU/CPU) is a production-grade path tracer built directly into 3ds Max. The photorealistic output quality for archviz, product shots, and film VFX is a primary reason teams choose 3ds Max.
- **V-Ray, Corona, Redshift, Octane plugin ecosystem.** The render plugin ecosystem for 3ds Max is the most mature in the DCC world — V-Ray is the archviz industry standard, Corona is widely used for interiors, Redshift and Octane for film. Kerf has no render plugin API.
- **Mature Edit Poly and Modifier Stack.** Industry-standard Edit Poly modeling with a non-destructive Modifier Stack (TurboSmooth, Chamfer, Bevel, Bend, Bend, etc.) refined over 35+ years. Kerf's feature tree covers engineering operations but not this mesh-modifier depth.
- **Animation, rigging, and simulation.** Full skeletal animation, IK/FK, CAT rig, Biped, morph targets, particle systems, and cloth simulation — a complete animation pipeline. Kerf has no plans to replicate these.
- **Archviz material and plugin libraries.** Chaos Cosmos, Forest Pack, RailClone, and extensive material libraries are purpose-built for architectural visualisation workflows.
- **35+ year community and training.** Extensive tutorials, certification programs, and a large community of archviz and game-art practitioners.

## What 3ds Max is not (for engineering use)

- **Not a B-rep CAD kernel.** 3ds Max models are polygon meshes, not boundary-representation solids. No analytically exact planes, cylinders, or spline-trimmed surfaces.
- **No STEP B-rep round-trip.** STEP and IGES transfer B-rep geometry that machines and CAM systems expect. 3ds Max exports via FBX/DWG; there is no native B-rep STEP writer.
- **No GD&T or technical drawings.** Engineering drawings with ASME Y14.5 geometric dimensioning and tolerancing are out of scope for 3ds Max by design.
- **Modifier Stack ≠ parametric feature history.** 3ds Max's Modifier Stack is linear per-object and destructive once applied. It does not maintain persistent face IDs.
- **No electronics, no engineering-calc breadth.** There is no schematic editor, no PCB router, no BOM, no simulation pre-compliance.

## Where Kerf is positioned differently

- **B-rep solids with valid topology and tolerances.** Kerf's OCCT kernel produces exact boundary-representation solids whose faces, edges, and vertices carry stable IDs for downstream features, drawings, and CAM paths.
- **Parametric feature history DAG.** The feature tree (pad, pocket, revolve, loft, fillet, draft) is a persistent directed acyclic graph. Editing an early feature regenerates all downstream geometry.
- **Multi-discipline in one workspace.** Electronics (schematic + PCB + DRC + Gerber), jewelry (ring v4, gemstones v2, settings v3/v4, chain v2), 2D drawings, GD&T, CNC CAM, and architecture (IFC) share one environment.
- **STEP / IGES / 3DM B-rep interop.** Manufacturing and supply-chain tooling expects B-rep geometry. Kerf reads and writes STEP and IGES; 3ds Max cannot.
- **MIT open-core, with a hosted option.** The core is permissively MIT-licensed (3ds Max is a subscription product at ~$235/mo as of May 2026). A hosted SaaS version runs in the browser; a single binary installs locally on Windows, macOS, and Linux.
- **Chat-native workflow.** Describe a change in plain language; the LLM edits the feature tree directly, backed by live doc-search.

## Honest gaps — where 3ds Max wins

- **Render quality.** Arnold, V-Ray, Corona, Redshift — production path-traced output with caustics, volumetrics, dispersion, and motion blur. Kerf's heroShot renderer (HDRI + ACES + bloom) is not in the same class for production archviz or VFX.
- **Poly modeling and Modifier Stack depth.** Edit Poly + 35 years of mesh modifiers give 3ds Max an unmatched mesh-first modeling capability. Kerf covers engineering operations but not this breadth.
- **Animation and rigging.** Skeletal animation, NLA, cloth, particles — a complete film/game pipeline. Kerf has no plans here.
- **Render plugin ecosystem.** The V-Ray/Corona/Redshift/Octane plugin ecosystem has no Kerf counterpart. Kerf has no render plugin API.
- **Archviz material libraries and production workflows.** Purpose-built archviz tools (Chaos Cosmos, Forest Pack, RailClone) and established production workflows for interior and exterior visualisation.
- **Community and ecosystem depth.** 35+ years of accumulated tutorials, add-ons, and asset packs for archviz and game art.

## Side by side

| Feature | 3ds Max | Kerf |
|---|---|---|
| License | ⚠️ Autodesk subscription | ✅ MIT open-core |
| Cost | ⚠️ ~$235/mo or ~$1,875/yr (May 2026) | ✅ Free local binary; pay-as-you-go hosted |
| Platform | ⚠️ Windows desktop only | ✅ Browser + Win/macOS/Linux binary |
| Hosted / cloud | ❌ Desktop only | ✅ Hosted SaaS + local install |
| B-rep solid kernel | ⚠️ Mesh-first (Edit Poly) — no B-rep | ✅ OCCT B-rep — exact rational geometry |
| Parametric history | ⚠️ Linear Modifier Stack — not persistent face-ID DAG | ✅ OCCT feature tree + persistent face IDs |
| Constraint sketcher | ❌ None | ✅ Sketcher v2 — geometric + dimensional constraints |
| STEP / IGES B-rep interop | ⚠️ Via FBX/DWG; STEP plugin import only | ✅ STEP / IGES / 3DM B-rep round-trip |
| Built-in renderer | ✅ Arnold (GPU/CPU path tracer) | ⚠️ HDRI + ACES + bloom (heroShot); no path tracer |
| Third-party render plugins | ✅ V-Ray, Corona, Redshift, Octane | ❌ No render plugin API yet |
| Caustics / GI / dispersion | ✅ Production caustics via Arnold/V-Ray/Corona | ⚠️ In progress (jewelry use case) |
| PBR materials | ✅ Physical Material + Slate editor | ⚠️ PBR material library in progress |
| Archviz material libraries | ✅ Chaos Cosmos, Forest Pack, etc. | ❌ None |
| Edit Poly / Modifier Stack | ✅ Industry-standard mesh modeling | ⚠️ SubD authoring + sculpt + remesh; no Modifier Stack |
| Animation / rigging | ✅ Full skeletal, IK/FK, CAT, particles | ❌ None |
| GD&T / tolerances | ❌ None | ✅ ASME Y14.5 datum + tolerance framework |
| 2D technical drawings | ❌ None | ✅ Multi-sheet drawings |
| Electronics / PCB | ❌ Not applicable | ✅ Full EDA — schematic, routing, DRC, Gerber/IPC-2581 |
| CNC CAM | ❌ None | ✅ 3-axis CAM + tool DB; 5-axis 3+2 |
| Chat / LLM editing | ❌ None | ✅ Chat-native — edits feature tree per turn |
| Scripting | ✅ MAXScript + Python 3 API | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
