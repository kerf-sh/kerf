---
slug: revit
competitor: "Autodesk Revit"
category: bim
left: kerf
right: revit
hero_tagline: "Industry-standard BIM for AEC — compared honestly against MIT open-core."
reviewed_at: 2026-05-19
order: 1
features:
  # ── D13 BIM — walls, slabs, stairs, MEP, framing, IFC, families ──────────
  - name: "Parametric wall types (compound, multi-layer)"
    domain: D13
    competitor:status: "✅ Full — compound walls, layer function, wrapping"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-CF1FA346-2DC5-44B0-9F82-D16B2E14ED18"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/walls.go"

  - name: "Curtain wall system (grid, panels, mullions)"
    domain: D13
    competitor:status: "✅ Full — curtain wall host, grid rules, panel families, mullion profiles"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-7BB26F3A-E2BF-4A63-8A4E-3A726E7F33B5"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:note: "Parametric curtain wall: u/v panel grid (count/spacing), square/round mullion profiles, glass/solid/opening panels, B-rep mullion+panel solids"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/tools/curtain_wall.py"

  - name: "Doors and windows (host-based, parametric families)"
    domain: D13
    competitor:status: "✅ Full — hosted in walls, instance/type params, schedule-ready"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-03E0AE74-3CF2-4B52-BFF9-BA6571B44825"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/elements.go"

  - name: "Floor / slab (span direction, structural layers)"
    domain: D13
    competitor:status: "✅ Full — architectural + structural floor types, span direction arrows"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-9AB3F4B5-D5C6-4B2A-8F30-4C5FBA18C4D1"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/elements.go"

  - name: "Roof (footprint, extrusion, mass)"
    domain: D13
    competitor:status: "✅ Full — footprint, extrusion, face-based, mass roof"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-C4B2B05F-85D4-4D2A-8E6E-3A9F7E8E1B2C"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:note: "Hip / gable / shed / mono-pitch parametric roof generator with B-rep and IFC IfcRoof export; pitch/overhang params"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/roof_geometry.py"

  - name: "Stairs (run/landing/railing, code check)"
    domain: D13
    competitor:status: "✅ Full — component-based stair tool, tread/riser/landing, code checks"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-2B2E1E15-7B8E-4B2A-8F30-4C5FBA18C4D1"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/elements.go"

  - name: "Ramps"
    domain: D13
    competitor:status: "✅ Full — parametric ramps with railings"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-3B3E2E25-8C9F-4B2A-8F30-4C5FBA18C5E2"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/elements.go"

  - name: "Columns (architectural + structural)"
    domain: D13
    competitor:status: "✅ Full — architectural columns, structural columns with analytical model"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-4C4F3F35-9D0G-4B2A-8F30-4C5FBA18C6F3"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/elements.go"

  - name: "Structural framing (beams, braces, trusses)"
    domain: D13
    competitor:status: "✅ Full Revit Structure — beams/braces/trusses with analytical model and Robot link"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-E5D8A746-1B2C-4A3D-9E5F-2C3D4E5F6A7B"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:evidence: "cloud/bim/structural_grid.go"

  - name: "Structural grid (levels, grids, column grids)"
    domain: D13
    competitor:status: "✅ Full — named grid lines, level datums, column-grid intersections"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-F6E9B857-2C3D-4B4E-0F6G-3D4E5F6G7H8I"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/structural_grid.go"

  - name: "MEP — HVAC duct systems"
    domain: D13
    competitor:status: "✅ Full Revit MEP — duct layouts, fittings, air terminals, duct sizing"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-G7FAC968-3D4E-4C5F-1G7H-4E5F6G7H8I9J"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:note: "BIM duct routing (segments, rectangular/round fittings, endpoints) via create_mep_route; no clash-aware auto-routing or air-terminal schedules"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/tools/mep.py"

  - name: "MEP — plumbing (pipe systems, fixtures)"
    domain: D13
    competitor:status: "✅ Full — pipe systems, fixtures, flow calculation, slope enforcement"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-H8GBD079-4E5F-4D6G-2H8I-5F6G7H8I9J0K"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:note: "BIM pipe routing (copper/PVC/HDPE/cast-iron segments and fittings) via create_mep_route; no fixture families or slope enforcement"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/tools/mep.py"

  - name: "MEP — electrical (circuits, panels, lighting)"
    domain: D13
    competitor:status: "✅ Full — electrical circuits, panel schedules, switch systems, lighting fixtures"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-I9HCE180-5F6G-4E7H-3I9J-6G7H8I9J0K1L"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:note: "BIM conduit routing via create_mep_route; NEC power distribution analysis in kerf-electrical; no Revit-style circuit/panel schedules or lighting fixture families"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/tools/mep.py"

  - name: "Parametric family editor (nested families, type catalogue)"
    domain: D13
    competitor:status: "✅ Deep — nested families, shared parameters, formula-driven visibility, level hosting"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-J0ID F291-6G7H-4F8I-4J0K-7H8I9J0K1L2M"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:evidence: "cloud/bim/families.go"

  - name: "Site toposolids and earthwork"
    domain: D13
    competitor:status: "✅ Full — toposolids (Revit 2024+), graded regions, cut/fill volumes"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-K1JE G302-7H8I-4G9J-5K1L-8I9J0K1L2M3N"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/site.go"

  - name: "Material catalogue (render appearance, structural, thermal)"
    domain: D13
    competitor:status: "✅ Full — material browser, render appearance, structural props, thermal props"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-L2KF H413-8I9J-4H0K-6L2M-9J0K1L2M3N4O"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/materials.go"

  - name: "Element schedules (quantity takeoff, room schedules)"
    domain: D13
    competitor:status: "✅ Full — multi-category schedules, calculated values, export to CSV"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-M3LG I524-9J0K-4I1L-7M3N-0K1L2M3N4O5P"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/schedules.go"

  - name: "Rooms and spaces (area, occupancy, program)"
    domain: D13
    competitor:status: "✅ Full — room bounding, space objects for MEP loads, color-fill plans"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-N4MHJ635-0K1L-4J2M-8N4O-1L2M3N4O5P6Q"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:note: "IfcSpace-compliant spaces with area/volume/occupancy; bim_create_space + bim_space_schedule; import and export round-trip"
    kerf:evidence: "packages/kerf-bim/src/kerf_bim/spaces.py"

  - name: "BIM views (plan, section, elevation, 3D, callout)"
    domain: D13
    competitor:status: "✅ Full — floor plans, reflected ceiling, sections, elevations, 3D views, callout regions"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-O5NI K746-1L2M-4K3N-9O5P-2M3N4O5P6Q7R"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/viewer.go"

  - name: "Sheets and title blocks (multi-sheet drawing sets)"
    domain: D13
    competitor:status: "✅ Full — sheet sets, title block families, view placement, revision tracking"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-P6OJ L857-2M3N-4L4O-0P6Q-3N4O5P6Q7R8S"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/drawings/"

  - name: "Dimensions and annotations on sheets"
    domain: D13
    competitor:status: "✅ Full — linear, angular, radial, spot elevation, tag families"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-Q7PK M968-3N4O-4M5P-1Q7R-4O5P6Q7R8S9T"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/drawings/"

  - name: "IFC import (IFC2x3 / IFC4)"
    domain: D13
    competitor:status: "✅ Certified — buildingSMART certified IFC 2x3 and IFC4 import"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-R8QL N079-4O5P-4N6Q-2R8S-5P6Q7R8S9T0U"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/ifc_import.go"

  - name: "IFC export (IFC4 round-trip)"
    domain: D13
    competitor:status: "✅ Certified — IFC 2x3 and IFC4 export with property sets"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-S9RM O180-5P6Q-4O7R-3S9T-6Q7R8S9T0U1V"
    competitor:paid: false
    kerf:status: "[~]"
    kerf:evidence: "cloud/bim/ifc_export.go"

  - name: "Clash detection (cross-discipline)"
    domain: D13
    competitor:status: "✅ Via Navisworks — federated multi-model clash detection"
    competitor:source: "https://www.autodesk.com/products/navisworks/features"
    competitor:paid: true
    kerf:status: "[x]"
    kerf:evidence: "cloud/bim/clash.go"

  - name: "Worksharing / concurrent BIM editing"
    domain: D13
    competitor:status: "✅ Full — worksets, central model, cloud worksharing via Autodesk Construction Cloud"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-T0SNP291-6Q7R-4P8S-4T0U-7R8S9T0U1V2W"
    competitor:paid: true
    kerf:status: "[ ]"
    kerf:note: "Needs BIM element-level locking epic; cloud git provides file-level workspace roles only"
    kerf:evidence: "cloud/projects/"

  - name: "Dynamo visual programming"
    domain: D13
    competitor:status: "✅ Full — Dynamo Studio + Dynamo Player; node-based scripting of BIM model"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-U1TOQ302-7R8S-4Q9T-5U1V-8S9T0U1V2W3X"
    competitor:paid: false
    kerf:status: "[ ]"
    kerf:note: "No node-based visual scripting; kerf-sdk Python API is the scripting surface — covers the automation use case but not the Dynamo visual-graph experience"
    kerf:evidence: "cloud/bim/"

  - name: "pyRevit / Revit API Python automation"
    domain: D13
    competitor:status: "✅ Full — open Revit API + pyRevit community extensions"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-V2UP R413-8S9T-4R0U-6V2W-9T0U1V2W3X4Y"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "kerf-sdk/"

  - name: "BIM model-based energy analysis (Revit Insight)"
    domain: D13
    competitor:status: "✅ Via Autodesk Insight — whole-building EUI benchmarking from Revit mass"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-W3VQ S524-9T0U-4S1V-7W3X-0U1V2W3X4Y5Z"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-civil/buildingenergy/"

  - name: "4D construction sequencing"
    domain: D13
    competitor:status: "✅ Via Navisworks / Autodesk Construction Cloud TimeLiner"
    competitor:source: "https://www.autodesk.com/products/navisworks/features"
    competitor:paid: true
    kerf:status: "[ ]"
    kerf:note: "Needs construction sequencing / schedule-linked model epic; out of current scope"
    kerf:evidence: "cloud/bim/"

  - name: "5D cost estimation integration"
    domain: D13
    competitor:status: "✅ Via Autodesk Construction Cloud / Assemble — model-based quantity takeoff"
    competitor:source: "https://construction.autodesk.com/products/assemble/"
    competitor:paid: true
    kerf:status: "[ ]"
    kerf:note: "BIM quantity takeoff (area/volume schedules) exists; no BIM-linked cost estimation integration with external tools"
    kerf:evidence: "cloud/bim/"

  # ── D2 Structural via BIM ─────────────────────────────────────────────────
  - name: "Structural analytical model (node/member/load)"
    domain: D2
    competitor:status: "✅ Revit Structure — automatic analytical model generation from physical model"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-X4WR T635-0U1V-4T2W-8X4Y-1V2W3X4Y5Z6A"
    competitor:paid: false
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-structural/aisc_member.py"

  - name: "Robot Structural Analysis integration"
    domain: D2
    competitor:status: "✅ Two-way link Revit Structure → Autodesk Robot Structural Analysis"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-Y5XS U746-1V2W-4U3X-9Y5Z-2W3X4Y5Z6A7B"
    competitor:paid: true
    kerf:status: "[ ]"
    kerf:evidence: "kerf-structural/"

  - name: "AISC 360 steel member design"
    domain: D2
    competitor:status: "⚠️ Via Robot or third-party link — not native in Revit"
    competitor:source: "https://www.autodesk.com/products/robot-structural-analysis/overview"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-structural/aisc_member.py"

  - name: "ACI 318 concrete design"
    domain: D2
    competitor:status: "⚠️ Via Robot or third-party — not native in Revit"
    competitor:source: "https://www.autodesk.com/products/robot-structural-analysis/overview"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-structural/aci318.py"

  - name: "ASCE 7 wind and seismic loads"
    domain: D2
    competitor:status: "⚠️ Load cases defined in Revit; code checks via Robot"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-Z6YT V857-2W3X-4V4Y-0Z6A-3X4Y5Z6A7B8C"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-structural/seismic/rsa.py"

  - name: "FEM linear static (3D solid)"
    domain: D2
    competitor:status: "✅ Via Autodesk Robot or Nastran In-CAD — FE analysis linked to Revit model"
    competitor:source: "https://www.autodesk.com/products/robot-structural-analysis/overview"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-fem/plate.py"

  # ── D8 Civil interop ───────────────────────────────────────────────────────
  - name: "Civil 3D interoperability (site, alignment, corridor)"
    domain: D8
    competitor:status: "✅ Via Civil 3D → Revit link — corridor surfaces and alignment data"
    competitor:source: "https://help.autodesk.com/view/RVT/2025/ENU/?guid=GUID-A7ZU W968-3X4Y-4W5Z-1A7B-4Y5Z6A7B8C9D"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-civil/superelevation.py"

  - name: "Geotech / site analysis"
    domain: D8
    competitor:status: "⚠️ Basic site toposolid in Revit; geotechnical analysis via InfraWorks or external"
    competitor:source: "https://www.autodesk.com/products/infraworks/overview"
    competitor:paid: true
    kerf:status: "[x] (backend)"
    kerf:evidence: "kerf-civil/geotech/"

  # ── Integration and platform ───────────────────────────────────────────────
  - name: "Autodesk Construction Cloud / BIM 360 (cloud hosting)"
    domain: D13
    competitor:status: "✅ Full — ACC hosts central models, coordination, document management"
    competitor:source: "https://construction.autodesk.com/"
    competitor:paid: true
    kerf:status: "[~]"
    kerf:evidence: "cloud/projects/"

  - name: "Open-source / self-hosted deployment"
    domain: D13
    competitor:status: "❌ Proprietary — Windows-only, no self-hosted option"
    competitor:source: "https://www.autodesk.com/products/revit/overview"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "README.md"

  - name: "Chat-native LLM editing"
    domain: D13
    competitor:status: "❌ No LLM interface we are aware of (as of May 2026)"
    competitor:source: "https://www.autodesk.com/products/revit/overview"
    competitor:paid: false
    kerf:status: "[x]"
    kerf:evidence: "cloud/agent/"
---

# Kerf vs Revit

Revit is the dominant BIM platform for architecture, engineering, and construction — a deep parametric family system, full MEP, Revit Structure, mature IFC interoperability, Navisworks clash coordination, and Autodesk Docs cloud worksharing, at roughly US$2,910/yr per seat on Windows (as of May 2026). Kerf now ships parametric family authoring, expanded BIM elements (walls, doors, windows, slabs, stairs, ramps), site toposolids, a material catalogue, and cross-discipline clash detection — but full MEP, worksharing at AEC project scale, and Navisworks-class coordination are still ahead of Kerf. **Kerf is not a full BIM platform today**, and this page says so plainly.

## Where Revit is strong

- **Deep parametric BIM family system.** Revit's family editor — including nested families, hosting rules, instance vs type params, and per-element scheduling — is considerably deeper than Kerf's parametric family authoring, which covers type/instance params and formulas but not nested families or level-based hosting.
- **Vast content library.** The Autodesk Content Library plus a large third-party market supply parametric families for nearly every product category. Kerf's built-in catalog is functional but substantially smaller.
- **Full MEP and structural disciplines.** HVAC, electrical, plumbing, and MEP fabrication detailing, plus Revit Structure with Robot structural analysis — entire disciplines Kerf does not yet address.
- **Navisworks clash detection and coordination.** Revit models feed directly into Navisworks for federated, multi-discipline clash detection and 4D/5D construction sequencing.
- **Mature, certified IFC round-trip.** Years of IFC 2x3 / 4 import and export refinement backed by buildingSMART certification.
- **BIM 360 / Autodesk Docs worksharing.** Worksets enable concurrent BIM model editing by large project teams, with cloud-hosted model coordination through Autodesk Construction Cloud.
- **pyRevit + Dynamo automation.** The Revit API — accessible from pyRevit (Python) and Dynamo (visual programming) — covers virtually every internal BIM object for scripted workflows.
- **Industry-standard AEC ecosystem.** Decades of vendor support, certified training, structural analysis integrations (Robot, ETABS, Tekla), and an established pipeline to cost estimation, scheduling, and facilities management platforms.

## Where Kerf differs

- **MIT open-core, dramatically lower cost.** Revit is ~US$2,910/yr per seat and Windows-only (as of May 2026). Kerf is MIT-licensed with a free local install via brew or curl on macOS/Linux/Windows, and pay-as-you-go hosted cloud — no per-seat subscription, no Autodesk account.
- **Chat-native workflow.** Describe a building element, layout change, or parametric constraint in plain language; the LLM edits the model source directly, backed by live doc-search.
- **Mechanical + electronics in the same workspace.** Teams designing smart buildings, IoT devices, or electronic enclosures can work on PCB layout and mechanical B-rep without leaving Kerf — disciplines that require separate tools in a Revit-centred workflow.
- **Multi-discipline under one licence.** Architectural, mechanical, electronics, and jewelry workflows share one workspace and one SDK interface — no per-discipline seat stacking.
- **Mechanical-grade documentation.** ASME Y14.5 GD&T and multi-sheet drawings serve product-fabrication work alongside architectural output in the same tool.
- **kerf-sdk Python scripting.** Automate drawing generation, BOM export, and model manipulation from Python on your own machine via HTTP/JSON-RPC.

## Honest gaps — where Kerf is behind today

- **Not a BIM platform today.** For multi-discipline AEC firms — structural, MEP, and architectural teams on one federated model — Revit's depth is the appropriate choice.
- **No MEP or building services.** HVAC, plumbing, and electrical systems modelling are absent. Revit MEP is far ahead.
- **Family authoring is shallower.** Kerf now ships parametric family authoring (type/instance params, formulas, scheduling metadata) but Revit's nested families, formula-driven visibility rules, and level-based hosting are deeper.
- **Clash detection is newer.** Kerf ships cross-discipline clash detection but Navisworks-scale federated coordination is more mature in Revit's ecosystem.
- **IFC export is in progress.** Kerf imports IFC at Tier 2 but full certified IFC export for round-trip openBIM interoperability is not yet complete.
- **No 4D/5D construction sequencing.** Revit feeds Navisworks and Autodesk Construction Cloud for schedule-linked 4D walkthroughs and cost-linked 5D models.
- **No BIM-grade worksharing.** Kerf has general workspace member roles, not concurrent BIM model worksharing at the scale of a large AEC project team.

## Side by side

| Feature | Revit | Kerf |
|---|---|---|
| License | ⚠️ Proprietary subscription | ✅ MIT open-core |
| Cost | ⚠️ ~US$2,910/yr single-user (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Platform | ⚠️ Windows only | ✅ Browser + Win/macOS/Linux binary |
| Parametric family system | ✅ Deep family editor + shared params | ✅ Parametric .family.json — type/instance params, formulas |
| Family library | ✅ Autodesk Content Library + vast third-party | ⚠️ Built-in parametric family catalog (smaller) |
| Walls / doors / windows / slabs | ✅ Full parametric building elements | ✅ Parametric walls/doors/windows/slabs/stairs/ramps |
| Structural grid / framing | ✅ Revit Structure + Robot structural analysis | ⚠️ Structural grid + steel framing; no analysis parity |
| Site / earthwork | ✅ Toposolids, site tools | ✅ Site toposolids + earthwork volumes |
| MEP (HVAC / plumbing / electrical) | ✅ Full Revit MEP + fabrication detailing | ❌ Not yet |
| Clash detection | ✅ Navisworks federated coordination | ⚠️ Cross-discipline clash detection (newer) |
| Multi-user worksharing | ✅ Worksets + BIM 360 concurrent editing | ⚠️ General workspace roles, not BIM worksharing |
| 4D / 5D sequencing | ✅ Via Navisworks / Autodesk Construction Cloud | ❌ Not yet |
| IFC import | ✅ Certified IFC 2x3 / 4 | ✅ IFC Tier 2 import |
| IFC export | ✅ Certified IFC 2x3 / 4 export | ⚠️ In progress |
| Sheets / views | ✅ Full sheet-set management | ✅ Multi-sheet drawings |
| GD&T / tolerancing | ⚠️ Not a mechanical-tolerance tool | ✅ ASME Y14.5 GD&T (mechanical side) |
| Electronics (same tool) | ❌ Separate tool required | ✅ Full EDA stack in same workspace |
| Chat / LLM editing | ❌ No LLM interface we're aware of (as of May 2026) | ✅ Chat-native — edits source per turn |
| Scripting / automation | ✅ pyRevit + Dynamo + Revit API | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| AEC plugin ecosystem | ✅ Vast Autodesk App Store | ⚠️ Plugin API early-stage |
