---
slug: archicad
competitor: Graphisoft ArchiCAD
category: bim
left: kerf
right: archicad
hero_tagline: "ArchiCAD pioneered BIM — Kerf brings engineering-grade precision to teams building beyond the building."
reviewed_at: 2026-05-24
features:
  - domain: D13
    feature: "BIM walls / slabs / framing"
    competitor:
      status: yes
      note: "Core Archicad wall, slab, beam, and column tools; full parametric intersections"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-1.htm"
    kerf:
      status: yes
      note: "kerf-bim walls/slabs/framing wired; parametric engine + IFC viewer"
      evidence: "packages/kerf-bim/src/bim.py"
  - domain: D13
    feature: "BIM stairs / ramps"
    competitor:
      status: yes
      note: "Stair Maker and ramp tool; parametric risers, treads, landings"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-20.htm"
    kerf:
      status: yes
      note: "Stairs and ramps in kerf-bim engine; viewer wired"
      evidence: "packages/kerf-bim/src/bim.py"
  - domain: D13
    feature: "BIM doors / windows"
    competitor:
      status: yes
      note: "Parametric door and window objects with frame, panel, and opening parameters"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-3.htm"
    kerf:
      status: yes
      note: "Parametric doors/windows in kerf-bim; wired in viewer"
      evidence: "packages/kerf-bim/src/bim.py"
  - domain: D13
    feature: "BIM roof generator"
    competitor:
      status: yes
      note: "Complex roof geometry: hip, gable, shed, barrel, mono-pitch — all parametric"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-9.htm"
    kerf:
      status: yes
      note: "Parametric hip / gable / shed / mono-pitch roof B-rep generator with IFC IfcRoof export"
      evidence: "packages/kerf-bim/src/kerf_bim/roof_geometry.py"
  - domain: D13
    feature: "IFC 4 authoring and export"
    competitor:
      status: yes
      note: "Full IFC 2x3 and IFC 4 authoring with certified buildingSMART export; complete property sets"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/070_interoperability/070_interoperability-1.htm"
    kerf:
      status: partial
      note: "IFC4 export wired (walls/slabs/doors/windows/spaces/stairs/openings/site); Tier 2 import; not yet buildingSMART certified"
      evidence: "packages/kerf-bim/src/kerf_bim/export_ifc/writer.py"
  - domain: D13
    feature: "GDL parametric object library"
    competitor:
      status: yes
      note: "Geometric Description Language objects — parametric families for every building product category"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/030_libraries/030_libraries-1.htm"
    kerf:
      status: partial
      note: "Parametric .family.json (type/instance params, formulas); no GDL-equivalent object market"
      evidence: "packages/kerf-bim/src/"
  - domain: D13
    feature: "MEP Modeler (HVAC / plumbing / electrical routing)"
    competitor:
      status: paid
      note: "Paid add-on: Graphisoft MEP Modeler; not in base Archicad Solo"
      source: "https://graphisoft.com/solutions/products/mep-modeler"
    kerf:
      status: partial
      note: "BIM MEP routing (duct/pipe/conduit segments, fittings, endpoints) via create_mep_route tool; no clash-aware auto-routing UI"
      evidence: "packages/kerf-bim/src/kerf_bim/tools/mep.py"
  - domain: D13
    feature: "Teamwork BIMcloud multi-user worksharing"
    competitor:
      status: paid
      note: "BIMcloud Basic included with Archicad; BIMcloud SaaS is a separate paid subscription"
      source: "https://graphisoft.com/solutions/products/bimcloud"
    kerf:
      status: partial
      note: "Cloud git workspace roles; not BIM element-level locking at AEC project scale"
      evidence: "cloud/git/"
  - domain: D13
    feature: "Schedules and quantity take-off"
    competitor:
      status: yes
      note: "Interactive schedules for doors, windows, materials, zones — live-linked to 3D model"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/060_documentation/060_documentation-5.htm"
    kerf:
      status: yes
      note: "BIM element schedules (walls/doors/windows/spaces/slabs); area/volume/occupancy totals per level; bim_space_schedule tool"
      evidence: "packages/kerf-bim/src/kerf_bim/tools/schedule.py"
  - domain: D13
    feature: "Curtain wall / curtain wall designer"
    competitor:
      status: yes
      note: "Parametric curtain wall tool with panel, frame, and corner connection logic"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-16.htm"
    kerf:
      status: yes
      note: "Parametric curtain wall: panel grid (u/v divisions, count/spacing), mullion profiles (square/round), glass/solid/opening panels, B-rep mullion + panel solids"
      evidence: "packages/kerf-bim/src/kerf_bim/tools/curtain_wall.py"
  - domain: D13
    feature: "Zone / room / space objects"
    competitor:
      status: yes
      note: "Zone tool defines spaces with area, volume, and occupancy data for energy and code compliance"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-13.htm"
    kerf:
      status: yes
      note: "IfcSpace-compliant space objects with area/volume/occupancy; bim_create_space + bim_space_schedule tools; IFC import + export of spaces wired"
      evidence: "packages/kerf-bim/src/kerf_bim/spaces.py"
  - domain: D13
    feature: "Hotlinked modules (XRef / federated model)"
    competitor:
      status: yes
      note: "Hotlink Manager links external Archicad files as live references into the host model"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/050_teamwork/050_teamwork-7.htm"
    kerf:
      status: no
      note: "No federated BIM hotlink/XRef mechanism; cloud git provides file-level references but not BIM-level live linking"
      evidence: ""
  - domain: D8
    feature: "Site terrain / mesh modelling"
    competitor:
      status: yes
      note: "Mesh tool + site modelling with cut-fill volume calculation"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-12.htm"
    kerf:
      status: partial
      note: "Backend geotech + earthwork volumes; no interactive site mesh UI"
      evidence: "packages/kerf-civil/geotech/"
  - domain: D1
    feature: "Parametric object model"
    competitor:
      status: yes
      note: "Every element is parametric with instance and type properties; 3D + 2D representation linked"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/010_concepts/010_concepts-1.htm"
    kerf:
      status: yes
      note: "Feature-tree parametric model; OCCT B-rep; sketch constraints via PlaneGCS"
      evidence: "packages/kerf-core/src/"
  - domain: D1
    feature: "2D technical drawings / documentation"
    competitor:
      status: yes
      note: "Layout book with floor plans, sections, elevations, annotations auto-generated from 3D model"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/060_documentation/060_documentation-1.htm"
    kerf:
      status: partial
      note: "Engineering multi-sheet drawings (template-based, not live B-rep projection); no layout book"
      evidence: "src/components/DrawingsView.jsx"
  - domain: D1
    feature: "3D solid B-rep modelling"
    competitor:
      status: yes
      note: "Underlying geometry via Graphisoft's own kernel; supports morph tool for free-form solids"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/020_elemtools/020_elemtools-15.htm"
    kerf:
      status: yes
      note: "Full OCCT B-rep; pad/pocket/revolve/sweep/loft/fillet/boolean wired"
      evidence: "packages/kerf-core/src/occt/"
  - domain: D1
    feature: "Sheet metal flat-pattern"
    competitor:
      status: no
      note: "Not applicable — Archicad is an architectural BIM tool, not a mechanical CAD tool"
      source: "https://graphisoft.com/solutions/products/archicad"
    kerf:
      status: partial
      note: "Single flange + unfold + flat DXF; no hem/relief/jog/multi-flange"
      evidence: "packages/kerf-core/src/sheetmetal.py"
  - domain: D1
    feature: "GD&T / tolerancing"
    competitor:
      status: no
      note: "Not applicable — architectural tool; no manufacturing tolerancing"
      source: "https://graphisoft.com/solutions/products/archicad"
    kerf:
      status: partial
      note: "GD&T data model (ASME Y14.5); no MBD/PMI on model view"
      evidence: "packages/kerf-core/src/gdandt.py"
  - domain: D4
    feature: "Building energy analysis export"
    competitor:
      status: yes
      note: "Direct export to EnergyPlus and IDA ICE for building energy simulation"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/070_interoperability/070_interoperability-6.htm"
    kerf:
      status: partial
      note: "Backend building loads (CLTD/RTS, ASHRAE Ch.18, degree-day); no energy simulation export"
      evidence: "packages/kerf-thermal/buildingenergy/transient.py"
  - domain: D4
    feature: "HVAC duct sizing"
    competitor:
      status: paid
      note: "Via MEP Modeler paid add-on; duct routing and sizing in the BIM model"
      source: "https://graphisoft.com/solutions/products/mep-modeler"
    kerf:
      status: yes
      note: "SMACNA duct sizing + flat-pattern (backend)"
      evidence: "packages/kerf-thermal/hvac/duct.py"
  - domain: D6
    feature: "PCB / electronics design"
    competitor:
      status: no
      note: "Not applicable — Archicad does not address electronics or EDA"
      source: "https://graphisoft.com/solutions/products/archicad"
    kerf:
      status: yes
      note: "Schematic + PCB layout (KiCad round-trip), ngspice SPICE, DRC — wired in browser"
      evidence: "src/components/SchematicView.jsx"
  - domain: D11
    feature: "Tolerance stackup / metrology"
    competitor:
      status: no
      note: "Not applicable — architectural BIM tool"
      source: "https://graphisoft.com/solutions/products/archicad"
    kerf:
      status: partial
      note: "1D WC/RSS/MC stackup + 3D vector-loop; no MBD on model"
      evidence: "packages/kerf-qa/tolstack/"
  - domain: D14
    feature: "Material cost / quantity schedules"
    competitor:
      status: yes
      note: "Element schedules with area, volume, and material quantities; export to Excel/CSV"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/060_documentation/060_documentation-5.htm"
    kerf:
      status: partial
      note: "Should-cost engine (backend) + BOM panel in assemblies; no BIM quantity take-off schedule"
      evidence: "packages/kerf-costing/src/"
  - domain: D14
    feature: "LCA / environmental data"
    competitor:
      status: partial
      note: "Limited via third-party Eco Designer extension; not in base Archicad"
      source: "https://graphisoft.com/solutions/products/eco-designer-stella"
    kerf:
      status: yes
      note: "Full ISO 14040/44 4-phase LCA; 6 impact categories + uncertainty (backend)"
      evidence: "packages/kerf-lca/phases.py"
  - domain: D13
    feature: "Python / open scripting API"
    competitor:
      status: partial
      note: "GDL (Geometric Description Language) — proprietary; JSON API (Archicad 25+) in beta"
      source: "https://help.graphisoft.com/AC/27/INT/_AC27_Help/content/080_scripting/080_scripting-1.htm"
    kerf:
      status: yes
      note: "kerf-sdk on PyPI; HTTP/JSON-RPC automation from any Python environment"
      evidence: "packages/kerf-sdk/README.md"
  - domain: D13
    feature: "LLM / chat-native editing"
    competitor:
      status: no
      note: "No LLM interface in Archicad as of May 2026"
      source: "https://graphisoft.com/solutions/products/archicad"
    kerf:
      status: yes
      note: "Chat-native: plain-language edits to feature tree and BIM model per turn"
      evidence: "src/components/ChatPanel.jsx"
---

# Kerf vs Graphisoft ArchiCAD

Graphisoft ArchiCAD (now owned by Nemetschek) invented Building Information Modelling (BIM) in 1987, before the term existed. It stores every building element — wall, slab, roof, door, window, stair — as a parametric object with properties (material, U-value, cost, fire rating), not just geometry. That data-richness is what distinguishes BIM from mere 3D drawing. ArchiCAD is used by architectural practices worldwide for everything from single-family homes to major public buildings. It is a domain-specific tool: it models buildings. Kerf is an engineering CAD tool that includes IFC support and structural grid primitives — it does not try to be a BIM authoring platform, but it can speak the same language.

## Where they converge

Both ArchiCAD and Kerf support IFC (Industry Foundation Classes) — the open standard for BIM data exchange. Kerf's IFC Tier 2 import means a building model authored in ArchiCAD can be brought into Kerf for coordination with structural engineering, MEP routing, or fabrication of specific components. Both tools produce parametric models: ArchiCAD's building elements have dimensional parameters; Kerf's mechanical features have sketch dimensions and feature parameters.

Both tools acknowledge that buildings include things other than architecture. ArchiCAD has MEP routing (Graphisoft MEP Modeler), structural grid, and coordination workflows; Kerf has a structural grid primitive, IFC import, and the ability to model the engineered components that go into a building — HVAC fittings, structural connections, facade panels — that a pure BIM authoring tool does not model with manufacturing precision.

## Where Kerf wins

- **Engineering fabrication precision.** ArchiCAD models buildings to architectural precision — a wall has a thickness and material, not a manufacturing tolerance. Kerf models to manufacturing precision: exact B-rep, GD&T-annotated drawings, flat-pattern sheet metal, and CNC-ready output. Facade contractors and structural fabricators who need to manufacture components from the model need Kerf, not ArchiCAD.
- **MIT open-core, no seat fee.** ArchiCAD licensing runs to thousands of dollars per seat per year (Solo and SME editions ~$180-250/mo as of May 2026; larger practice editions higher). Kerf is MIT-licensed — free locally.
- **Electronics and multi-domain.** ArchiCAD is buildings only. Kerf covers PCB schematic and layout, pre-compliance simulation, and mechanical engineering in the same workspace — relevant for smart building components, automation panels, and building-integrated electronics.
- **Chat-native workflow.** Describe a design change in plain language and the LLM edits the feature tree. ArchiCAD has no LLM interface we're aware of (as of May 2026).
- **Python scripting API.** Kerf exposes a kerf-sdk on PyPI for HTTP/JSON-RPC automation. ArchiCAD's scripting is GDL (Geometric Description Language) — a proprietary domain-specific language with a much steeper learning curve.

## Where ArchiCAD wins

- **Purpose-built BIM authoring.** ArchiCAD's wall tool, slab tool, roof generator, stair maker, curtain wall designer, and door/window library are purpose-built for architectural design. A wall knows it is a wall: it intersects cleanly with other walls, carries fire-rating data, and appears in a schedule automatically. Kerf has no equivalent domain objects.
- **IFC authoring depth.** ArchiCAD produces rich, property-set-complete IFC files where every element carries classification, material, cost, fire rating, and energy data. Kerf can import IFC Tier 2 but does not author IFC natively.
- **Energy analysis.** ArchiCAD exports to EnergyPlus and IDA ICE for building energy simulation via direct export. Kerf has no building energy analysis.
- **Documentation workflow.** ArchiCAD's integrated layout book, floor plan generation from the 3D model, section/elevation automation, and annotation system is designed for full architectural documentation packages. Kerf's drawing layer targets engineering technical drawings.
- **Teamwork (multi-user BIM).** ArchiCAD's Teamwork feature (BIMcloud) provides multi-user concurrent BIM authoring with element-level locking. Kerf's cloud collaboration is file-level (cloud git).

## Feature matrix

| Feature | Kerf | Graphisoft ArchiCAD |
|---|---|---|
| License | MIT open-core | Proprietary subscription |
| Cost | Free local; hosted credits | ~$180-250+/seat/mo (May 2026) |
| Primary domain | Engineering CAD (multi-discipline) | Architectural BIM authoring |
| Parametric model | Feature tree (mechanical) | Building elements (wall/slab/roof/etc.) |
| IFC support | Tier 2 import | Full IFC authoring + export |
| Technical drawings | Engineering multi-sheet + GD&T | Architectural layout book + floor plans |
| Sheet metal | Yes (flange + unfold) | Not applicable |
| PCB / electronics | In-box | Not applicable |
| Energy simulation | Not yet | EnergyPlus / IDA ICE export |
| Multi-user collaboration | Cloud git | BIMcloud Teamwork |
| Chat / LLM editing | Chat-native | None known (as of May 2026) |
| Python scripting | kerf-sdk on PyPI | GDL (proprietary domain language) |
| STEP export | Yes | Limited (via IFC) |
| Open source | Yes (MIT) | No |
| Building-specific objects | Structural grid (limited) | Full AEC object library |

## Both speak IFC

ArchiCAD and Kerf both work with IFC (Industry Foundation Classes, ISO 16739). An ArchiCAD project exported to IFC can be imported into Kerf for engineering coordination — fabricating facade panels, modelling MEP components with manufacturing tolerance, or integrating building-embedded electronics. IFC is the handshake between the architect's BIM and the engineer's CAD model.

---
*Last reviewed: 2026-05-24. Competitor information sourced from public Graphisoft ArchiCAD product pages. Kerf capabilities reflect the current shipped product.*
