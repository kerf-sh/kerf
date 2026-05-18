---
slug: vectorworks
competitor: Vectorworks
category: cad-architecture
left: kerf
right: vectorworks
hero_tagline: "Vectorworks spans architecture, landscape, and entertainment — Kerf spans mechanical, electronics, and fabrication."
---

# Kerf vs Vectorworks

Vectorworks (developed by Vectorworks Inc., a Nemetschek subsidiary) is a multi-discipline design platform used primarily in architecture, landscape architecture, interior design, and entertainment/event design (stage, lighting, rigging). Unlike ArchiCAD or Revit, which are purpose-built for building construction BIM, Vectorworks serves a broader set of spatial designers — including landscape architects who need grading and plant schedules, and entertainment designers who need lighting plots and rigging geometry. Pricing is subscription-based (~$263/yr for Fundamentals to ~$3,695/yr for Architect+Landmark+Spotlight bundles). Kerf is MIT open-core engineering CAD focused on mechanical, electronics, and fabrication workflows.

## Where they converge

Both Vectorworks and Kerf support hybrid 2D/3D workflows. Vectorworks is famous for its 2D drafting heritage (it descended from MiniCAD in the 1980s) and its ability to work simultaneously in 2D plan and 3D model. Kerf's drawing layer similarly connects 2D technical drawings to the 3D feature model. Both tools export DXF, making them interoperable with AutoCAD-based workflows.

Both tools acknowledge that design does not live in a single discipline. Vectorworks bundles Architect, Landmark, and Spotlight into combined packages for multi-discipline firms. Kerf bundles mechanical CAD, electronics, and a scripting API. The shared philosophy is that a designer should not switch tools mid-project.

Both tools also have a Python scripting interface. Vectorworks exposes Vectorscript and a Python API; Kerf exposes kerf-sdk on PyPI via HTTP/JSON-RPC.

## Where Kerf wins

- **Engineering fabrication precision.** Vectorworks produces drawings and 3D geometry for construction documents — not manufacturing-precision B-rep with tolerances, GD&T, and flat-pattern sheet metal. For fabricating components from the model (custom facade panels, structural connections, stage rigging hardware), Kerf's OCCT B-rep is the appropriate tool.
- **MIT open-core, no subscription.** Vectorworks ranges from ~$263/yr to ~$3,695/yr depending on the bundle. Kerf is MIT-licensed — free locally with no feature gating.
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
| Cost | Free local; hosted credits | ~$263–$3,695/yr (bundle-dependent) |
| Primary disciplines | Mechanical, electronics, fabrication | Architecture, landscape, entertainment |
| 2D drafting | Technical drawings (downstream of 3D) | Native 2D drafting + 3D (mature) |
| IFC support | Tier 2 import | IFC export (Architect edition) |
| Landscape design | Not included | Full grading + plant + irrigation (Landmark) |
| Entertainment / stage | Not included | Full lighting plot + rigging (Spotlight) |
| Sheet metal | Yes (flange + unfold + flat-pattern) | Not included |
| PCB / electronics | In-box (full stack + pre-compliance) | Not included |
| Chat / LLM editing | Chat-native | None |
| Python scripting | kerf-sdk on PyPI | Vectorscript + Python API |
| STEP export | Yes | Limited (via 3D export) |
| DXF export | Yes | Yes |
| Open source | Yes (MIT) | No |
| Community | Early-stage | Established (architecture + entertainment) |

## Both export DXF

Vectorworks and Kerf both export AutoCAD DXF, which is the lingua franca for exchanging 2D geometry between design tools. A Vectorworks floor plan exported to DXF can be imported into Kerf for engineering dimensioning or integration with fabricated components — and a Kerf technical drawing can be exported to DXF for use in a Vectorworks construction document set.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Vectorworks product pages. Kerf capabilities reflect the current shipped product.*
