---
slug: sketchup
competitor: Trimble SketchUp
category: cad-architecture
left: kerf
right: sketchup
hero_tagline: "SketchUp made 3D intuitive for architects — Kerf brings engineering precision to the same audience."
reviewed_at: 2026-05-24
features:
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: no
      note: "Push-pull surface modeller — no constraint sketcher, no geometric/dimensional constraints"
      source: "https://help.sketchup.com/en/sketchup/getting-started-sketchup"
    kerf:
      status: yes
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-cad-core/src/sketcher/"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: no
      note: "Push/pull extrusion only — no feature history, no revolve operation"
      source: "https://help.sketchup.com/en/sketchup/push-pull"
    kerf:
      status: yes
      note: "OCCT, wired"
      evidence: "packages/kerf-cad-core/src/features/"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: no
      note: "Polygon mesh — no B-rep kernel; intersect faces approximation only"
      source: "https://help.sketchup.com/en/sketchup/modeling-complex-3d-shapes"
    kerf:
      status: yes
      note: "OCCT exact B-rep booleans; no graceful failure handling / fuzzy heal"
      evidence: "packages/kerf-cad-core/src/occt/"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: no
      note: "No mate/constraint system; components placed by hand, no parametric assembly"
      source: "https://help.sketchup.com/en/sketchup/components-overview"
    kerf:
      status: yes
      note: "Coincident/concentric/parallel mates wired; BOM panel"
      evidence: "packages/kerf-cad-core/src/assembly/"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: partial
      note: "LayOut produces presentation sheets, not standards-compliant engineering drawings; no live B-rep projection"
      source: "https://help.sketchup.com/en/layout/getting-started-layout"
    kerf:
      status: partial
      note: "Live HLR projection (make2d) + auto-dim; no GD&T-placement UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/make2d.py"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: no
      note: "No sheet metal tooling, no unfold/flat-pattern"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF (K-factor); no auto corner-relief"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D2
    feature: "Structural member design (AISC/ACI)"
    competitor:
      status: no
      note: "No structural analysis; architecture visualisation tool only"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "AISC 360-22 + ACI 318-19 + NDS 2018 + Eurocodes; backend"
      evidence: "kerf-structural/"

  - domain: D2
    feature: "FE — plate / shell / solid"
    competitor:
      status: no
      note: "No FEA capability"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "MITC4 plate/shell + CalculiX solid bridge; backend only"
      evidence: "kerf-fem/"

  - domain: D3
    feature: "Gear rating (AGMA / ISO 6336)"
    competitor:
      status: no
      note: "No machine element calculators"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "AGMA 2001-D04 + ISO 6336 Method B; backend"
      evidence: "kerf-mechanical/gearstrength/"

  - domain: D3
    feature: "Shaft / bearing / fastener sizing"
    competitor:
      status: no
      note: "No engineering sizing calculators"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "ISO 281 + ISO/TS 16281 bearings, VDI 2230 fasteners, shaft stress; backend"
      evidence: "kerf-mechanical/"

  - domain: D4
    feature: "Thermal / HVAC analysis"
    competitor:
      status: no
      note: "No thermal or HVAC calculation; visualisation only"
      source: "https://www.sketchup.com/products/sketchup-studio"
    kerf:
      status: yes
      note: "Psychrometrics, LMTD/ε-NTU heat exchangers, SMACNA duct sizing, building loads; backend"
      evidence: "kerf-thermal/"

  - domain: D5
    feature: "Aerodynamic / structural analysis"
    competitor:
      status: no
      note: "No aero, marine, or space analysis"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "VLM + viscous + compressibility; orbital mechanics; naval hydrostatics; backend"
      evidence: "kerf-aero/"

  - domain: D6
    feature: "Schematic / PCB (EDA)"
    competitor:
      status: no
      note: "No EDA capability — architecture tool only"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "KiCad round-trip viewer + tscircuit PCB; SPICE via ngspice; wired"
      evidence: "packages/kerf-ecad/"

  - domain: D6
    feature: "SPICE simulation"
    competitor:
      status: no
      note: "No simulation capability"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "Real ngspice wired; binary .raw not yet parsed"
      evidence: "packages/kerf-ecad/spice/"

  - domain: D7
    feature: "3-axis CAM (toolpaths / G-code)"
    competitor:
      status: no
      note: "No CAM; models exported to separate CAM software"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "CAMView wired; profile/contour/pocket/face; Fanuc/GRBL/LinuxCNC posts"
      evidence: "packages/kerf-cam/"

  - domain: D7
    feature: "FDM slicing"
    competitor:
      status: no
      note: "No slicer; STL export only for third-party slicers"
      source: "https://help.sketchup.com/en/sketchup/exporting-3d-model-file"
    kerf:
      status: yes
      note: "Cura bridge wired (PrintSliceView)"
      evidence: "packages/kerf-cam/slicing/"

  - domain: D8
    feature: "Civil / geo analysis"
    competitor:
      status: no
      note: "Sandbox terrain tools only; no engineering analysis"
      source: "https://help.sketchup.com/en/sketchup/creating-terrain-sandbox-tools"
    kerf:
      status: yes
      note: "Alignment, pavement, geotech, hydrology, geodesy; backend"
      evidence: "kerf-civil/"

  - domain: D9
    feature: "Dynamics / motion / controls"
    competitor:
      status: no
      note: "No kinematics, dynamics, or controls simulation"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "Planar MBD, 6-DOF IK, SDOF/n-DOF vibration, LQR/Kalman; backend"
      evidence: "kerf-motion/"

  - domain: D10
    feature: "PLC / firmware (IEC 61131-3)"
    competitor:
      status: no
      note: "No PLC or firmware tooling"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim + firmware build/upload/debug; wired"
      evidence: "packages/kerf-plc/"

  - domain: D10
    feature: "Solar PV system analysis"
    competitor:
      status: partial
      note: "Studio includes Trimble SolarEdge solar analysis (shade/irradiance on geometry); not a full PV sizing tool"
      source: "https://www.sketchup.com/products/sketchup-studio"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + global MPPT + mismatch loss; backend"
      evidence: "kerf-energy/solarpv/"

  - domain: D11
    feature: "Tolerance stackup / GD&T"
    competitor:
      status: no
      note: "No tolerancing, GD&T, or metrology capability"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "ASME Y14.5 data model; 1D WC/RSS/MC + 3D vector loop; backend"
      evidence: "kerf-qa/tolstack/"

  - domain: D12
    feature: "Optics / acoustics analysis"
    competitor:
      status: no
      note: "No optics or acoustics simulation"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "Paraxial ABCD + Seidel + non-sequential RT; ISO 9613 + RT60 acoustics; backend"
      evidence: "kerf-optics/"

  - domain: D13
    feature: "BIM (IFC export)"
    competitor:
      status: partial
      note: "Studio only: IFC4 export with limited schema coverage; free/Go/Pro tiers export OBJ/DWG/DXF, not IFC"
      source: "https://help.sketchup.com/en/sketchup/ifc-import-and-export"
    kerf:
      status: yes
      note: "Revit-comparable BIM engine + IFC Tier 2 viewer via /compile-ifc"
      evidence: "packages/kerf-bim/"

  - domain: D13
    feature: "Jewelry design"
    competitor:
      status: no
      note: "No jewelry-specific tooling; general polygon modelling only"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "41 jewelry modules; full configurator UI — RhinoGold/Matrix-class"
      evidence: "packages/kerf-jewelry/"

  - domain: D14
    feature: "Should-cost / material selection / LCA"
    competitor:
      status: no
      note: "No costing, material selection, or lifecycle assessment capability"
      source: "https://www.sketchup.com/products/sketchup-pro"
    kerf:
      status: yes
      note: "Boothroyd-Dewhurst should-cost; Ashby material selection (200 materials); ISO 14040/44 LCA; backend"
      evidence: "kerf-cost/"
---

# Kerf vs Trimble SketchUp

Trimble SketchUp is one of the most accessible 3D modelling tools ever built. Originally created at Google and later acquired by Trimble, it lowered the barrier to 3D for architects, interior designers, urban planners, and hobbyists. Its push/pull direct modelling, face-inference engine, and Extensions Warehouse made it the first 3D tool many designers ever learned. SketchUp Pro, SketchUp Studio, and the subscription-based SketchUp Go are Trimble's commercial offerings; a free web version exists with significant limitations. Kerf is an engineering CAD tool — more precise, more parametric, and more multi-disciplinary than SketchUp, but also more complex.

## Where they converge

Both SketchUp and Kerf are used for architectural and building design contexts. Both can model buildings, rooms, and spatial layouts. Both have a web-based interface option (SketchUp's free web app; Kerf's hosted browser-based environment). Both acknowledge that geometry ultimately needs to leave the tool — SketchUp exports DWG, DXF, and IFC; Kerf exports STEP, IGES, IFC Tier 2, and DXF.

Both tools are also used by non-traditional engineering users — hobbyists, makers, and designers who are not mechanical engineers by training. Both lean into accessibility, though SketchUp does so more aggressively with its push/pull paradigm, while Kerf uses a chat interface to lower the barrier to parametric precision.

## Where Kerf wins

- **Parametric history and constraints.** SketchUp is a direct modelling tool — there is no feature tree, no constraint sketcher, and no parametric history. Change a dimension and you re-model. Kerf's feature tree means a design intent is encoded: change a parameter and the downstream geometry updates.
- **Engineering precision.** SketchUp is notoriously imprecise — its face-snapping geometry engine accumulates small errors that cause trouble in downstream fabrication. Kerf's OCCT B-rep kernel maintains exact geometric relationships with no approximation.
- **Sheet metal, PCB, and multi-domain.** SketchUp is architecture and visualisation. Kerf covers mechanical sheet metal (flange/unfold/flat-pattern), PCB schematic and layout, pre-compliance electronics simulation, and scripting — none of which SketchUp touches.
- **MIT open-core, no subscription.** SketchUp Pro costs ~$349/yr; SketchUp Studio with Scan Essentials and V-Ray is ~$699/yr (as of May 2026). Kerf is MIT-licensed — free locally with no feature gating.
- **Technical drawings.** Kerf produces associative multi-sheet technical drawings with GD&T, tolerances, and title blocks. SketchUp's LayOut tool produces presentation drawings but not standards-compliant engineering documents.

## Where SketchUp wins

- **Ease of entry.** Push/pull modelling with face inference is the most intuitive way to create a 3D box ever designed. A person with no CAD experience can model a building in SketchUp in an hour. Kerf requires understanding feature-based thinking.
- **Architectural visualisation.** SketchUp's rendering ecosystem (V-Ray integration, Enscape, Lumion workflows, photorealistic style plugins) is built around architectural presentation — sunlight studies, material libraries, client-facing renders. Kerf has a basic PBR viewport.
- **Extensions Warehouse.** Thousands of free and commercial plugins cover everything from stair generators to terrain tools to structural section libraries. Kerf's extension ecosystem is nascent.
- **BIM-adjacent workflow.** SketchUp Studio with Scan Essentials supports point cloud import, solar analysis, and IFC export that sits at the intersection of BIM and quick architectural modelling. Kerf's IFC support is Tier 2 import only.
- **Community scale.** SketchUp has tens of millions of registered users, a massive 3D Warehouse of downloadable models, and a tutorial ecosystem spanning YouTube, books, and courses in dozens of languages. Kerf is early-stage.

## Feature matrix

| Feature | Kerf | Trimble SketchUp Pro |
|---|---|---|
| License | MIT open-core | Proprietary subscription |
| Cost | Free local; hosted credits | ~$349/yr (Pro) / ~$699/yr (Studio) (May 2026) |
| Modelling paradigm | Parametric feature tree + sketcher | Direct push/pull (no feature history) |
| Precision / tolerances | Exact B-rep (OCCT) | Approximate (face-inference, small-error accumulation) |
| Constraint sketcher | Sketcher v2 | None |
| Sheet metal | Flange + hem + jog + multi-flange + unfold + flat DXF | Not included |
| Technical drawings | Multi-sheet + GD&T | LayOut (presentation, not engineering standard) |
| IFC export | IFC Tier 2 import | IFC export (Studio) |
| PCB / electronics | In-box | Not applicable |
| Chat / LLM editing | Chat-native | None we're aware of (as of May 2026) |
| Rendering | Basic PBR viewport | V-Ray (Studio), Enscape (plugin) |
| Extension ecosystem | Early-stage | Massive (Extensions Warehouse) |
| Community | Early-stage | Tens of millions of users |
| Open source | Yes (MIT) | No |
| STEP export | Yes | No (DWG / DXF / IFC / KMZ) |

## Both export IFC

SketchUp Studio and Kerf both produce IFC (Industry Foundation Classes) output. IFC is the open standard for building information interchange — a SketchUp model exported to IFC can be consumed by Kerf's IFC Tier 2 import and vice versa. This makes the two tools interoperable in AEC workflows where SketchUp handles the architectural massing and Kerf handles structural or MEP engineering elements.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Trimble SketchUp product pages. Kerf capabilities reflect the current shipped product.*
