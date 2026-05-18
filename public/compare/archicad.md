---
slug: archicad
competitor: Graphisoft ArchiCAD
category: cad-architecture
left: kerf
right: archicad
hero_tagline: "ArchiCAD pioneered BIM — Kerf brings engineering-grade precision to teams building beyond the building."
---

# Kerf vs Graphisoft ArchiCAD

Graphisoft ArchiCAD (now owned by Nemetschek) invented Building Information Modelling (BIM) in 1987, before the term existed. It stores every building element — wall, slab, roof, door, window, stair — as a parametric object with properties (material, U-value, cost, fire rating), not just geometry. That data-richness is what distinguishes BIM from mere 3D drawing. ArchiCAD is used by architectural practices worldwide for everything from single-family homes to major public buildings. It is a domain-specific tool: it models buildings. Kerf is an engineering CAD tool that includes IFC support and structural grid primitives — it does not try to be a BIM authoring platform, but it can speak the same language.

## Where they converge

Both ArchiCAD and Kerf support IFC (Industry Foundation Classes) — the open standard for BIM data exchange. Kerf's IFC Tier 2 import means a building model authored in ArchiCAD can be brought into Kerf for coordination with structural engineering, MEP routing, or fabrication of specific components. Both tools produce parametric models: ArchiCAD's building elements have dimensional parameters; Kerf's mechanical features have sketch dimensions and feature parameters.

Both tools acknowledge that buildings include things other than architecture. ArchiCAD has MEP routing (Graphisoft MEP Modeler), structural grid, and coordination workflows; Kerf has a structural grid primitive, IFC import, and the ability to model the engineered components that go into a building — HVAC fittings, structural connections, facade panels — that a pure BIM authoring tool does not model with manufacturing precision.

## Where Kerf wins

- **Engineering fabrication precision.** ArchiCAD models buildings to architectural precision — a wall has a thickness and material, not a manufacturing tolerance. Kerf models to manufacturing precision: exact B-rep, GD&T-annotated drawings, flat-pattern sheet metal, and CNC-ready output. Facade contractors and structural fabricators who need to manufacture components from the model need Kerf, not ArchiCAD.
- **MIT open-core, no seat fee.** ArchiCAD licensing runs to thousands of dollars per seat per year (Solo and SME editions ~$180-250/mo; larger practice editions higher). Kerf is MIT-licensed — free locally.
- **Electronics and multi-domain.** ArchiCAD is buildings only. Kerf covers PCB schematic and layout, pre-compliance simulation, and mechanical engineering in the same workspace — relevant for smart building components, automation panels, and building-integrated electronics.
- **Chat-native workflow.** Describe a design change in plain language and the LLM edits the feature tree. ArchiCAD has no LLM interface.
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
| Cost | Free local; hosted credits | ~$180-250+/seat/mo |
| Primary domain | Engineering CAD (multi-discipline) | Architectural BIM authoring |
| Parametric model | Feature tree (mechanical) | Building elements (wall/slab/roof/etc.) |
| IFC support | Tier 2 import | Full IFC authoring + export |
| Technical drawings | Engineering multi-sheet + GD&T | Architectural layout book + floor plans |
| Sheet metal | Yes (flange + unfold) | Not applicable |
| PCB / electronics | In-box | Not applicable |
| Energy simulation | Not yet | EnergyPlus / IDA ICE export |
| Multi-user collaboration | Cloud git | BIMcloud Teamwork |
| Chat / LLM editing | Chat-native | None |
| Python scripting | kerf-sdk on PyPI | GDL (proprietary domain language) |
| STEP export | Yes | Limited (via IFC) |
| Open source | Yes (MIT) | No |
| Building-specific objects | Structural grid (limited) | Full AEC object library |

## Both speak IFC

ArchiCAD and Kerf both work with IFC (Industry Foundation Classes, ISO 16739). An ArchiCAD project exported to IFC can be imported into Kerf for engineering coordination — fabricating facade panels, modelling MEP components with manufacturing tolerance, or integrating building-embedded electronics. IFC is the handshake between the architect's BIM and the engineer's CAD model.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Graphisoft ArchiCAD product pages. Kerf capabilities reflect the current shipped product.*
