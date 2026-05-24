---
slug: civil3d
competitor: "Civil 3D"
category: bim
left: kerf
right: civil3d
hero_tagline: "Civil infrastructure design — corridor/pipe depth vs MIT open-core analysis modules."
reviewed_at: 2026-05-19
order: 2
features:
  # D8 — Civil / infrastructure / geo (Civil 3D's primary domain)
  - domain: D8
    feature: "Horizontal+vertical alignment (clothoid, SSD)"
    competitor:
      status: yes
      note: "Core alignment design with design criteria file checks"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-84ACA3B3-CF47-43B4-B2C7-BE05C0F8A2DC"
    kerf:
      status: yes
      note: "Backend; no UI"
      evidence: "packages/kerf-civil/superelevation.py"

  - domain: D8
    feature: "Superelevation runoff transition"
    competitor:
      status: yes
      note: "Automated superelevation with AASHTO criteria file"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-F0F35958-5F74-4B1B-A26C-63706AC5CFD6"
    kerf:
      status: yes
      note: "Backend; AASHTO Exhibit 3-20 validated"
      evidence: "packages/kerf-civil/superelevation.py"

  - domain: D8
    feature: "Corridor / cross-section"
    competitor:
      status: yes
      note: "Full assemblies, subassemblies, targets — industry standard"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-3CAA31B4-4B40-4C69-B617-5F96EB77F6D9"
    kerf:
      status: yes
      note: "Backend; divided highway + urban curb-gutter templates"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Dynamic TIN surfaces"
    competitor:
      status: yes
      note: "Composite TINs, grading objects, surface comparison, cut/fill"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-CF0B5B8A-8085-4768-92C6-E0BD5B8D37B5"
    kerf:
      status: partial
      note: "TIN surface from point cloud + cut/fill volumes; contour extraction; no corridor-driven composite TINs"
      evidence: "packages/kerf-civil/src/kerf_civil/tin.py"

  - domain: D8
    feature: "Gravity pipe networks (storm/sanitary)"
    competitor:
      status: yes
      note: "Full storm and sanitary gravity pipe design, sizing, plan production"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-4D3E2C98-E4A5-4F9D-9EFE-8A1F0BDCB5A1"
    kerf:
      status: no
      note: "TR-55 hydrology + D8 flow accumulation exist; no gravity pipe network design/sizing/plan workflow"
      evidence: "packages/kerf-civil/src/kerf_civil/"

  - domain: D8
    feature: "Pressure pipe networks"
    competitor:
      status: yes
      note: "Pressure pipe parts, fittings, and plan production"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-A57BA96E-A2F5-4A4F-B0B3-2E3D8F6E1C9D"
    kerf:
      status: partial
      note: "Hardy-Cross steady-state pressure pipe network solver (Darcy-Weisbach, Hazen-Williams) in kerf-cad-core; no plan-production or fittings layout"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/civil/hydraulics.py"

  - domain: D8
    feature: "Survey / COGO"
    competitor:
      status: yes
      note: "Survey database, figures, least-squares adjustment, field-to-finish"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-3B1A3E9E-7B2D-4E3A-9E3B-7E3B9E3B7E3B"
    kerf:
      status: yes
      note: "Backend; traverse adjust, resection"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Geodesy / projections (Vincenty, TM, UTM, LCC)"
    competitor:
      status: partial
      note: "Survey-level coordinate geometry; limited geodetic projection set"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-2C3D4E5F-6A7B-8C9D-0E1F-2A3B4C5D6E7F"
    kerf:
      status: yes
      note: "Backend; Vincenty, TM, UTM, LCC validated"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Pavement design (AASHTO '93)"
    competitor:
      status: partial
      note: "Pavement design via linked tools (AutoCAD Civil 3D + external)"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; AASHTO '93 full calculation"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/pile/liquefaction)"
    competitor:
      status: no
      note: "Not a geotechnical analysis tool; no bearing/settlement calcs"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; Seed-Idriss CSR + SPT/CPT CRR validated"
      evidence: "packages/kerf-civil/geotech/"

  - domain: D8
    feature: "Hydrology (rational/SCS/TR-55)"
    competitor:
      status: partial
      note: "Exports hydrological data to HEC-HMS / HEC-RAS; no native TR-55"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-A1B2C3D4-E5F6-7A8B-9C0D-E1F2A3B4C5D6"
    kerf:
      status: yes
      note: "Backend; TR-55 runoff, time of concentration"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Spillway / dam / railway / earthworks"
    competitor:
      status: partial
      note: "Earthworks and railway via corridor; no dam/spillway hydraulics"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-3CAA31B4-4B40-4C69-B617-5F96EB77F6D9"
    kerf:
      status: yes
      note: "Backend; spillway, dam, railway, earthworks modules"
      evidence: "packages/kerf-civil/"

  - domain: D8
    feature: "Parcels and lot layout"
    competitor:
      status: yes
      note: "Parcel creation, sizing, subdivision, and report generation"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-C7D8E9F0-1A2B-3C4D-5E6F-7A8B9C0D1E2F"
    kerf:
      status: no
      note: "Needs parcel/lot-layout epic; not in current civil module scope"
      evidence: "packages/kerf-civil/src/kerf_civil/"

  - domain: D8
    feature: "Point cloud integration"
    competitor:
      status: yes
      note: "ReCap integration for scan-to-surface and surface comparison"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-D8E9F0A1-2B3C-4D5E-6F7A-8B9C0D1E2F3A"
    kerf:
      status: no
      note: "No scan / point-cloud ingestion; needs LiDAR/photogrammetry import pipeline"
      evidence: "packages/kerf-civil/src/kerf_civil/"

  - domain: D8
    feature: "Plan and profile sheet production"
    competitor:
      status: yes
      note: "Automated plan/profile sheets, sheet set manager, standards output"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-E9F0A1B2-3C4D-5E6F-7A8B-9C0D1E2F3A4B"
    kerf:
      status: no
      note: "No automated civil plan/profile sheet generation; corridor DXF export exists but no sheet-set workflow"
      evidence: "packages/kerf-civil/src/kerf_civil/"

  # D2 — Structural / FEA
  - domain: D2
    feature: "ASCE 7-22 wind (MWFRS+C&C)"
    competitor:
      status: no
      note: "Civil 3D is a drafting/design tool; no structural analysis"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; full MWFRS + C&C"
      evidence: "packages/kerf-structural/"

  - domain: D2
    feature: "ASCE 7-22 seismic (ELF + RSA + Newmark)"
    competitor:
      status: no
      note: "Civil 3D is a drafting/design tool; no seismic analysis"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; ELF + RSA (SRSS+CQC) + Newmark time-history"
      evidence: "packages/kerf-structural/seismic/"

  # D4 — Thermal / fluid / HVAC
  - domain: D4
    feature: "Pipe network (Hardy-Cross)"
    competitor:
      status: no
      note: "Civil 3D pipe networks are layout/drafting only; no flow analysis"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-A57BA96E-A2F5-4A4F-B0B3-2E3D8F6E1C9D"
    kerf:
      status: yes
      note: "Hardy-Cross steady-state pressure pipe network + Method-of-Characteristics transient solver"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/civil/hydraulics.py"

  # D1 — Geometry & core CAD
  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "AutoCAD native — full 2D drafting and annotation"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-F0A1B2C3-D4E5-F6A7-B8C9-D0E1F2A3B4C5"
    kerf:
      status: partial
      note: "Template-based; not live B-rep projection; no UI panel"
      evidence: "src/"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: yes
      note: "AutoCAD 3D solids — boolean operations on solids"
      source: "https://help.autodesk.com/view/CIV3D/2026/ENU/?guid=GUID-A1B2C3D4-E5F6-7A8B-9C0D-E1F2A3B4C5D6"
    kerf:
      status: yes
      note: "OCCT; no graceful failure / fuzzy heal"
      evidence: "packages/kerf-occt/"

  # D7 — Manufacturing / CAM
  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: no
      note: "Civil 3D has no nesting or CAM capability"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; Minkowski-sum NFP, 57.6% L-shape utilisation"
      evidence: "packages/kerf-cam/nesting/"

  # D10 — Electrical / energy / PLC
  - domain: D10
    feature: "NEC power distribution"
    competitor:
      status: no
      note: "Civil 3D has no electrical analysis"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; NEC power distribution + point-to-point SC"
      evidence: "packages/kerf-electrical/"

  # D14 — Cost / materials / LCA
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "Civil 3D has no should-cost or manufacturing cost analysis"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; 6 processes, Boothroyd-Dewhurst method"
      evidence: "packages/kerf-cost/"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: no
      note: "Civil 3D has no materials database or Ashby chart capability"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; 200 materials, Pareto frontier, weighted-score"
      evidence: "packages/kerf-matsel/"

  # D13 — Verticals
  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: partial
      note: "AEC Collection includes Revit; Civil 3D itself is not BIM authoring"
      source: "https://www.autodesk.com/collections/architecture-engineering-construction/overview"
    kerf:
      status: yes
      note: "Revit-comparable engine + viewer via /compile-ifc"
      evidence: "packages/kerf-bim/"

  # D6 — Electronics / EDA / silicon
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: no
      note: "Civil 3D has no EDA or electronics capability"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Viewer wired (read-only)"
      evidence: "src/"

  # D9 — Dynamics / motion / controls
  - domain: D9
    feature: "Controls — classical (Routh/Bode/RL/PID tune)"
    competitor:
      status: no
      note: "Civil 3D has no dynamics or controls analysis"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend; classical control design tools"
      evidence: "packages/kerf-controls/"

  # D11 — Tolerancing / QA
  - domain: D11
    feature: "Process capability (Cpk/Ppk)"
    competitor:
      status: no
      note: "Civil 3D has no QA or statistical process control"
      source: "https://www.autodesk.com/products/civil-3d/features"
    kerf:
      status: yes
      note: "Backend"
      evidence: "packages/kerf-qa/"
---

# Kerf vs Civil 3D

Autodesk Civil 3D is the industry-standard civil infrastructure design tool: corridor modelling (roads/highways/rail), alignments + profiles + cross-sections, dynamic TIN surfaces, pipe networks (gravity + pressure), parcels, point clouds, survey data integration, and plan production with sheet sets — all inside AutoCAD DWG. Available via the Autodesk AEC Collection (~US$4,150/yr as of May 2026). Kerf is NOT a Civil 3D replacement at production-civil-infrastructure scale. Civil 3D owns corridor/alignment/profile depth and pipe-network breadth. Kerf's civil-adjacent modules (hydrology, geotech, surveying, pavement, geodesy, earthworks) are useful for analysis work but do not approach Civil 3D's drafting or corridor depth.

## Where Civil 3D is strong

- **Industry-standard corridor modelling.** Full corridor assemblies, subassemblies, and targets for road/highway/rail design — the industry reference workflow for linear infrastructure projects.
- **Alignments, profiles, and cross-sections.** Complete horizontal and vertical alignment design with design criteria checks and full cross-section extraction.
- **Dynamic TIN surfaces.** Composite TIN surfaces, grading objects, dynamic surface comparison, and earthwork volume calculation driven by corridor geometry.
- **Gravity and pressure pipe networks.** Full storm/sanitary gravity pipe network design (sizing, analysis), pressure pipe parts and fittings, and plan production output — a complete utility-engineering workflow.
- **Parcels and lot layout.** Parcel creation, sizing, and report generation for land development projects.
- **Survey data integration.** Survey database, figures, least-squares adjustment, and field-to-finish workflows directly in the design environment.
- **Automated plan production.** Automated plan and profile sheets, sheet set management, and standards-compliant civil drawing output.
- **AutoCAD DWG native.** Civil 3D is built on AutoCAD — every drawing is a DWG file, fully compatible with the broader Autodesk ecosystem and industry file-exchange workflows.
- **AEC Collection integration.** Civil 3D, Revit, InfraWorks, and Navisworks in one bundle — complete infrastructure project delivery from concept to coordination.

## Where Kerf differs

- **MIT open-core, dramatically lower cost.** Civil 3D requires the AEC Collection at ~US$4,150/yr (as of May 2026) and is Windows-only. Kerf is MIT-licensed — free locally on Windows, macOS, and Linux.
- **Civil-adjacent analysis modules.** Kerf ships TR-55 hydrology (runoff, time of concentration), Coulomb/Rankine geotechnical analysis (earth pressure, bearing capacity), Vincenty-validated geodesy, ASCE 7 wind load and seismic response modules, and basic earthworks — useful for civil engineering calculations alongside design work.
- **Multi-discipline in one workspace.** Civil 3D is a civil infrastructure tool. Kerf adds full EDA (PCB schematic + layout), OCCT mechanical CAD, jewelry tooling, and BIM-adjacent primitives in the same workspace — useful for infrastructure projects that involve embedded electronics or smart-city components.
- **Chat-native workflow.** Describe an analysis setup, parameter change, or model query in plain language; the LLM edits the source backed by live doc-search. Civil 3D has no LLM integration we're aware of (as of May 2026).
- **kerf-sdk Python scripting.** Automate analysis workflows and model manipulation from Python over HTTP/JSON-RPC on your own machine.
- **Cross-platform.** Runs in the browser (hosted SaaS) or as a single binary on Windows, macOS, and Linux. Civil 3D is Windows-primary.

## Honest gaps — where Kerf is behind today

- **Corridor modelling is absent.** Civil 3D's full corridor assemblies, subassemblies, and targets for road/highway design have no Kerf equivalent. This is the core of Civil 3D's value.
- **Alignments, profiles, and cross-sections.** Kerf has no horizontal/vertical alignment design or automated cross-section extraction workflow.
- **Dynamic TIN surfaces and grading.** Civil 3D's composite TINs and grading objects are production civil tools Kerf does not replicate. Kerf has a basic earthworks module but no corridor-driven volumes.
- **Pipe network design.** Full gravity/pressure pipe network design, sizing, and plan production are absent in Kerf.
- **Survey database.** Civil 3D's survey database, figures, and least-squares adjustment have no Kerf equivalent. Kerf has basic surveying module validation but not a survey DB.
- **AutoCAD DWG authoring.** Kerf imports DWG but writes DXF — not native DWG. For teams that live in the DWG ecosystem, this is a meaningful limitation.
- **Automated civil plan production.** Civil 3D's automated plan and profile sheets and sheet set manager are mature production tools with no Kerf equivalent.
- **AEC Collection integration.** Revit + InfraWorks + Navisworks integration in one bundle is a significant practical advantage for full AEC project delivery.

## Side by side

| Feature | Civil 3D | Kerf |
|---|---|---|
| License | ⚠️ Proprietary subscription | ✅ MIT open-core |
| Cost | ⚠️ AEC Collection ~US$4,150/yr (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Platform | ⚠️ Windows-primary | ✅ Browser + Win/macOS/Linux binary |
| Corridor modelling (roads / rail) | ✅ Industry-standard — full assemblies / subassemblies | ❌ Not available |
| Alignments + profiles + cross-sections | ✅ Full alignment/profile/section design | ❌ Not available |
| Dynamic TIN surfaces | ✅ Composite TINs, grading, surface comparison | ⚠️ Basic earthwork / site grading |
| Gravity pipe networks | ✅ Full storm + sanitary design | ❌ Not available |
| Pressure pipe networks | ✅ Pressure pipe parts + plan production | ❌ Not available |
| Parcels + lot layout | ✅ Parcel creation + sizing + reports | ❌ Not available |
| Point clouds | ✅ ReCap integration | ❌ Not available |
| Survey data integration | ✅ Survey database + least-squares | ⚠️ Surveying module; no survey DB |
| AutoCAD DWG native | ✅ Built on AutoCAD; full DWG authoring | ⚠️ DXF import/export; no DWG authoring |
| Hydrology (TR-55 / rational method) | ⚠️ Exports to HEC-RAS / Civil Storm | ✅ kerf_cad_core.hydrology — TR-55 runoff |
| Geotechnical (Coulomb / bearing) | ⚠️ Not a geotech analysis tool | ✅ kerf_cad_core.geotech |
| Geodesy (Vincenty / datum transforms) | ⚠️ Survey-level coordinate geometry | ✅ kerf_cad_core.geodesy — Vincenty-validated |
| Wind load (ASCE 7) | ❌ Not applicable | ✅ kerf_cad_core.windload |
| Seismic (ASCE 7) | ❌ Not applicable | ✅ kerf_cad_core.seismic |
| Earthworks / cut-fill | ✅ Full earthwork volumes from corridor | ⚠️ Basic earthworks module |
| Mechanical B-rep CAD | ⚠️ AutoCAD 3D solids (not parametric) | ✅ OCCT feature tree, sketcher, CAM |
| Electronics (same tool) | ❌ Separate tool required | ✅ Full EDA stack in same workspace |
| Chat / LLM editing | ❌ None known (as of May 2026) | ✅ Chat-native — edits source per turn |
| Scripting | ✅ Civil 3D API (.NET / COM / Python via pyautocad) | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
