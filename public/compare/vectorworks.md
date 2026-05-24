---
slug: vectorworks
competitor: Vectorworks
category: cad-architecture
left: kerf
right: vectorworks
hero_tagline: "Vectorworks spans architecture, landscape, and entertainment — Kerf spans mechanical, electronics, and fabrication."
reviewed_at: 2026-05-24
features:
  # ── D1 Geometry & core CAD ──────────────────────────────────────────────
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "2D constraint-based drafting via Vectorworks SmartCursor + parametric objects"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FObjects_edit2%2FEditing_Constraints.htm"
    kerf:
      status: yes
      note: "PlaneGCS WASM sketcher wired; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-sketcher/planegcs_wasm/"

  - domain: D1
    feature: "3D solid modelling (pad / pocket / revolve / sweep / loft)"
    competitor:
      status: yes
      note: "Subdivision + NURBS + solid push-pull; ACIS-based kernel (Fundamentals and above)"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FObjects_edit2%2F3D_Modeling_Overview.htm"
    kerf:
      status: yes
      note: "OCCT pad/pocket/revolve/sweep fully wired; loft lacks guide-rail overload"
      evidence: "packages/kerf-occt/bindings/"

  - domain: D1
    feature: "NURBS surface modelling"
    competitor:
      status: yes
      note: "Native NURBS curves and surfaces including subdivision; Vectorworks Designer tier"
      source: "https://www.vectorworks.net/architect/features"
    kerf:
      status: partial
      note: "OCCT NURBS math complete; browser WASM bindings unconfirmed at build"
      evidence: "packages/kerf-occt/nurbs/"

  - domain: D1
    feature: "2D technical drawings (views / dimensions / sections)"
    competitor:
      status: yes
      note: "Mature 2D drafting heritage (descended from MiniCAD 1985); full annotation suite"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FAnnotation%2FAnnotating_Drawings.htm"
    kerf:
      status: partial
      note: "Template-based drawings; not live B-rep projection; no UI panel"
      evidence: "packages/kerf-drawings/"

  - domain: D1
    feature: "DXF / DWG import-export"
    competitor:
      status: yes
      note: "Full DXF/DWG round-trip including 3D; all Vectorworks tiers"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FImport_Export%2FImporting_and_Exporting_DXF_DWG.htm"
    kerf:
      status: yes
      note: "DXF export wired"
      evidence: "packages/kerf-export/dxf.ts"

  - domain: D1
    feature: "STEP / IGES export"
    competitor:
      status: partial
      note: "3D STEP export available; round-trip fidelity limited vs dedicated MCAD tools"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FImport_Export%2FImporting_and_Exporting_STEP_Files.htm"
    kerf:
      status: yes
      note: "OCCT STEP export wired"
      evidence: "packages/kerf-export/step.ts"

  - domain: D1
    feature: "Symbol / component library"
    competitor:
      status: yes
      note: "Vectorworks Cloud Library with thousands of architecture, landscape, and entertainment symbols"
      source: "https://www.vectorworks.net/community/vectorworks-service-select/cloud-library"
    kerf:
      status: yes
      note: "Parts library + BOM panel wired; community library early-stage"
      evidence: "src/components/LibraryPanel.jsx"

  # ── D7 Manufacturing / CAM ───────────────────────────────────────────────
  - domain: D7
    feature: "Flat-pattern / sheet-metal unfold"
    competitor:
      status: no
      note: "No sheet-metal unfold or flat-pattern DXF output"
      source: "https://www.vectorworks.net/architect/features"
    kerf:
      status: yes
      note: "Single flange + unfold + flat DXF wired; no hem/relief/jog/multi-flange"
      evidence: "packages/kerf-sheetmetal/"

  - domain: D7
    feature: "CNC / CAM toolpath output"
    competitor:
      status: no
      note: "No integrated CAM or G-code generation; geometry exported to CAM software"
      source: "https://www.vectorworks.net/architect/features"
    kerf:
      status: yes
      note: "3-axis CAM wired in CAMView; profile/contour/pocket/face ops"
      evidence: "src/components/CAMView.jsx"

  # ── D8 Civil / infrastructure / geo ─────────────────────────────────────
  - domain: D8
    feature: "Site grading and earthworks (DTM)"
    competitor:
      status: paid
      note: "Vectorworks Landmark: DTM-based grading, cut/fill volumes, grade limits; Landmark tier only"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FSite_Model%2FCreating_Site_Models.htm"
    kerf:
      status: yes
      note: "Contour extraction (marching squares), cut/fill volumes (prismatic), planar grade application; landscape_contours + landscape_cut_fill tools"
      evidence: "packages/kerf-landscape/src/kerf_landscape/grading.py"

  - domain: D8
    feature: "Contour manipulation and slope analysis"
    competitor:
      status: paid
      note: "Landmark: contour editing, slope shading, and 2D/3D site model analysis"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FSite_Model%2FAnalyzing_Site_Models.htm"
    kerf:
      status: yes
      note: "Marching-squares iso-contour extraction from DEM grid; grade_surface applies uniform planar grade; landscape_contours tool"
      evidence: "packages/kerf-landscape/src/kerf_landscape/grading.py"

  - domain: D8
    feature: "Hardscape design and area calculation"
    competitor:
      status: paid
      note: "Vectorworks Landmark: hardscape objects, surface area, material takeoffs"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FHardscapes%2FHardscape_Objects.htm"
    kerf:
      status: yes
      note: "Paver pattern generator (running-bond/stack-bond/herringbone-45/basketweave) + material takeoff; retaining wall (Rankine) sizing; landscape_paver_pattern + landscape_retaining_wall tools"
      evidence: "packages/kerf-landscape/src/kerf_landscape/hardscape.py"

  - domain: D8
    feature: "Irrigation layout"
    competitor:
      status: paid
      note: "Landmark: irrigation objects, head placement, zone scheduling"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FIrrigation%2FIrrigation_Overview.htm"
    kerf:
      status: yes
      note: "Irrigation zone scheduling (head spacing, zone flow demand, weekly run-time schedule, DU audit); ASABE/ICC 802-2014; landscape_irrigation_schedule tool"
      evidence: "packages/kerf-landscape/src/kerf_landscape/irrigation.py"

  # ── D12 Optics / rendering / acoustics ───────────────────────────────────
  - domain: D12
    feature: "Photorealistic rendering engine"
    competitor:
      status: yes
      note: "Renderworks (Cinema 4D engine): physically-based rendering, HDRI, caustics, global illumination"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FRendering%2FRenderworks_Overview.htm"
    kerf:
      status: no
      note: "No integrated renderer; geometry exported to external tools"
      evidence: ""

  - domain: D12
    feature: "Real-time OpenGL / GPU viewport"
    competitor:
      status: yes
      note: "Shaded, Final Quality Renderworks, and OpenGL real-time modes; all tiers"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FRendering%2FRendering_Overview.htm"
    kerf:
      status: yes
      note: "Three.js WebGL viewport wired; PBR materials"
      evidence: "src/components/Viewport3D.jsx"

  - domain: D12
    feature: "Lighting simulation (luminance / lux)"
    competitor:
      status: yes
      note: "Renderworks light objects with intensity, color, falloff; IES file support"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FRendering%2FLighting_Overview.htm"
    kerf:
      status: no
      note: "Photonics backend exists (LED/photodiode); no lux/luminance scene simulation"
      evidence: "packages/kerf-optics/photonics.py"

  # ── D13 Verticals ────────────────────────────────────────────────────────
  - domain: D13
    feature: "BIM walls / slabs / framing"
    competitor:
      status: paid
      note: "Vectorworks Architect: parametric wall, slab, column, beam objects with BIM data"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FWalls%2FWalls_Overview.htm"
    kerf:
      status: yes
      note: "kerf-bim walls/slabs/framing engine wired via /compile-ifc"
      evidence: "packages/kerf-bim/"

  - domain: D13
    feature: "BIM stairs and railings"
    competitor:
      status: paid
      note: "Vectorworks Architect: parametric stair and railing objects; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FStairs%2FStairs_Overview.htm"
    kerf:
      status: yes
      note: "kerf-bim stair geometry engine included"
      evidence: "packages/kerf-bim/stairs.py"

  - domain: D13
    feature: "IFC4 export / import (open BIM round-trip)"
    competitor:
      status: paid
      note: "Vectorworks Architect: certified IFC4 export; IFC import for coordination; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FImport_Export%2FExporting_IFC_Files.htm"
    kerf:
      status: yes
      note: "IFC4 engine + viewer via /compile-ifc; BIMView null-feed visual QA pending"
      evidence: "packages/kerf-bim/ifc4.py"

  - domain: D13
    feature: "Space / room objects and area schedule"
    competitor:
      status: paid
      note: "Vectorworks Architect: Space objects with automatic area/occupancy scheduling; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FSpaces%2FSpaces_Overview.htm"
    kerf:
      status: partial
      note: "Interior space-planning engine exists (backend only); no UI route"
      evidence: "packages/kerf-verticals/interior.py"

  - domain: D13
    feature: "Door and window parametric objects"
    competitor:
      status: paid
      note: "Vectorworks Architect: parametric doors and windows with BIM properties; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FDoors_Windows%2FDoors_and_Windows_Overview.htm"
    kerf:
      status: yes
      note: "kerf-bim door/window parametric objects included"
      evidence: "packages/kerf-bim/"

  - domain: D13
    feature: "Curtain wall / storefront"
    competitor:
      status: paid
      note: "Vectorworks Architect: curtain wall tool with panel and mullion configuration; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FCurtain_Walls%2FCurtain_Wall_Overview.htm"
    kerf:
      status: yes
      note: "Parametric curtain wall: u/v panel grid (count/spacing/mixed), square/round mullion profiles, glass/solid/opening panels, B-rep mullion+panel solids"
      evidence: "packages/kerf-bim/src/kerf_bim/tools/curtain_wall.py"

  - domain: D13
    feature: "Roof and ceiling modelling"
    competitor:
      status: paid
      note: "Vectorworks Architect: roof face/gable/hip tools, ceiling objects; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FRoofs%2FRoofs_Overview.htm"
    kerf:
      status: yes
      note: "kerf-bim roof geometry engine included"
      evidence: "packages/kerf-bim/"

  - domain: D13
    feature: "Plant/tree symbols with scheduling"
    competitor:
      status: paid
      note: "Vectorworks Landmark: plant symbols, plant list schedule, botanical database; Landmark tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FPlants%2FPlants_Overview.htm"
    kerf:
      status: yes
      note: "Xeriscape plant catalogue (USDA zone + WUCOLS water-use filtering); planting-grid spacing; annual water budget (WUCOLS ET factors); landscape_plants tool"
      evidence: "packages/kerf-landscape/src/kerf_landscape/planting.py"

  - domain: D13
    feature: "Entertainment / theatrical lighting plot"
    competitor:
      status: paid
      note: "Vectorworks Spotlight: lighting instrument symbols, plot automation, Vision integration; Spotlight tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FSpotlight%2FSpotlight_Overview.htm"
    kerf:
      status: no
      note: "No entertainment design domain"
      evidence: ""

  - domain: D13
    feature: "Rigging geometry and load analysis (Braceworks)"
    competitor:
      status: paid
      note: "Braceworks add-on: truss/rigging objects, structural load analysis for entertainment; Spotlight tier"
      source: "https://www.vectorworks.net/braceworks"
    kerf:
      status: no
      note: "No rigging domain; structural beam/truss engines not adapted for entertainment"
      evidence: ""

  - domain: D13
    feature: "Visual scripting (Marionette)"
    competitor:
      status: yes
      note: "Marionette: node-based visual programming for parametric geometry; all paid tiers"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FMarionette%2FMarionette_Overview.htm"
    kerf:
      status: no
      note: "No node-based visual scripting; kerf-sdk Python API is the scripting surface"
      evidence: ""

  - domain: D13
    feature: "Python scripting API"
    competitor:
      status: yes
      note: "Vectorworks Python API + Vectorscript; all paid tiers"
      source: "https://developer.vectorworks.net/index.php/Python_Scripting"
    kerf:
      status: yes
      note: "kerf-sdk on PyPI; HTTP/JSON-RPC; runs on user's machine"
      evidence: "packages/kerf-sdk/"

  # ── D14 Cost / materials / LCA ───────────────────────────────────────────
  - domain: D14
    feature: "BIM quantity takeoff / materials schedule"
    competitor:
      status: paid
      note: "Vectorworks Architect: area, volume, material schedules from BIM objects; Architect tier"
      source: "https://app-help.vectorworks.net/2024/eng/index.htm#t=VW2024_Guide%2FWorksheets%2FCreating_Worksheets.htm"
    kerf:
      status: yes
      note: "BOM panel wired; geometry-driven material quantity from assemblies"
      evidence: "src/components/BOMPanel.jsx"

  - domain: D14
    feature: "Should-cost estimation"
    competitor:
      status: no
      note: "No integrated should-cost or manufacturing cost model"
      source: "https://www.vectorworks.net/architect/features"
    kerf:
      status: yes
      note: "Should-cost engine (6 processes, Boothroyd-Dewhurst) — backend only"
      evidence: "packages/kerf-cost/"
---

# Kerf vs Vectorworks

Vectorworks (developed by Vectorworks Inc., a Nemetschek subsidiary) is a multi-discipline design platform used primarily in architecture, landscape architecture, interior design, and entertainment/event design (stage, lighting, rigging). Unlike ArchiCAD or Revit, which are purpose-built for building construction BIM, Vectorworks serves a broader set of spatial designers — including landscape architects who need grading and plant schedules, and entertainment designers who need lighting plots and rigging geometry. Pricing is subscription-based (~$263/yr for Fundamentals to ~$3,695/yr for Architect+Landmark+Spotlight bundles, as of May 2026). Kerf is MIT open-core engineering CAD focused on mechanical, electronics, and fabrication workflows.

## Where they converge

Both Vectorworks and Kerf support hybrid 2D/3D workflows. Vectorworks is famous for its 2D drafting heritage (it descended from MiniCAD in the 1980s) and its ability to work simultaneously in 2D plan and 3D model. Kerf's drawing layer similarly connects 2D technical drawings to the 3D feature model. Both tools export DXF, making them interoperable with AutoCAD-based workflows.

Both tools acknowledge that design does not live in a single discipline. Vectorworks bundles Architect, Landmark, and Spotlight into combined packages for multi-discipline firms. Kerf bundles mechanical CAD, electronics, and a scripting API. The shared philosophy is that a designer should not switch tools mid-project.

Both tools also have a Python scripting interface. Vectorworks exposes Vectorscript and a Python API; Kerf exposes kerf-sdk on PyPI via HTTP/JSON-RPC.

## Where Kerf wins

- **Engineering fabrication precision.** Vectorworks produces drawings and 3D geometry for construction documents — not manufacturing-precision B-rep with tolerances, GD&T, and flat-pattern sheet metal. For fabricating components from the model (custom facade panels, structural connections, stage rigging hardware), Kerf's OCCT B-rep is the appropriate tool.
- **MIT open-core, no subscription.** Vectorworks ranges from ~$263/yr to ~$3,695/yr depending on the bundle (as of May 2026). Kerf is MIT-licensed — free locally with no feature gating.
- **Electronics and PCB.** Vectorworks covers no electronics domain. Kerf ships PCB schematic, layout, pre-compliance simulation, and full fab output in the same workspace — relevant for entertainment tech (networked DMX controllers, LED driver boards) and smart building components.
- **Chat-native workflow.** Describe a feature in plain language; the LLM edits the feature tree backed by live doc-search. Vectorworks has no LLM interface.
- **Exact B-rep kernel.** Kerf's OCCT kernel maintains exact geometric relationships. Vectorworks' 3D geometry is ACIS-based with a stronger 2D drafting heritage — adequate for construction documents, less precise for CNC fabrication.

## Where Vectorworks wins

- **Landscape architecture.** Vectorworks Landmark has grading tools, contour manipulation, plant symbols with scheduling, irrigation layout, hardscape calculation, and site analysis — a complete landscape design workflow that Kerf does not approach.
- **Entertainment / event design.** Vectorworks Spotlight has lighting instrument symbols, lighting plot automation, rigging geometry, and integration with lighting control software (Vision, Braceworks for load analysis). Kerf has no entertainment design domain.
- **2D drafting heritage.** Vectorworks' 2D drafting tools — with intelligent walls, spaces, dimensions, and a rich symbol library — are mature in ways that Kerf's 2D drawing layer (which is downstream of the 3D model) is not.
- **Construction document production.** Vectorworks Architect produces the full set of architectural construction documents — floor plans, reflected ceiling plans, elevations, sections, schedules — in a workflow that architectural practices rely on daily.
- **BIM data for AEC.** Vectorworks exports IFC with building element properties for coordination with structural, MEP, and contractor teams. Kerf's IFC support is Tier 2 import only.

## Feature matrix

| Feature | Kerf | Vectorworks |
|---|---|---|
| License | MIT open-core | Proprietary subscription |
| Cost | Free local; hosted credits | ~$263–$3,695/yr (bundle-dependent, May 2026) |
| Primary disciplines | Mechanical, electronics, fabrication | Architecture, landscape, entertainment |
| 2D drafting | Technical drawings (downstream of 3D) | Native 2D drafting + 3D (mature) |
| IFC support | Tier 2 import | IFC export (Architect edition) |
| Landscape design | Not included | Full grading + plant + irrigation (Landmark) |
| Entertainment / stage | Not included | Full lighting plot + rigging (Spotlight) |
| Sheet metal | Yes (flange + unfold + flat-pattern) | Not included |
| PCB / electronics | In-box (full stack + pre-compliance) | Not included |
| Chat / LLM editing | Chat-native | No LLM interface we're aware of (as of May 2026) |
| Python scripting | kerf-sdk on PyPI | Vectorscript + Python API |
| STEP export | Yes | Limited (via 3D export) |
| DXF export | Yes | Yes |
| Open source | Yes (MIT) | No |
| Community | Early-stage | Established (architecture + entertainment) |

## Both export DXF

Vectorworks and Kerf both export AutoCAD DXF, which is the lingua franca for exchanging 2D geometry between design tools. A Vectorworks floor plan exported to DXF can be imported into Kerf for engineering dimensioning or integration with fabricated components — and a Kerf technical drawing can be exported to DXF for use in a Vectorworks construction document set.

---
*Last reviewed: 2026-05-24. Competitor information sourced from public Vectorworks product pages. Kerf capabilities reflect the current shipped product.*
