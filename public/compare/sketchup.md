---
slug: sketchup
competitor: Trimble SketchUp
category: cad-architecture
left: kerf
right: sketchup
hero_tagline: "SketchUp made 3D intuitive for architects — Kerf brings engineering precision to the same audience."
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
- **MIT open-core, no subscription.** SketchUp Pro costs ~$349/yr; SketchUp Studio with Scan Essentials and V-Ray is ~$699/yr. Kerf is MIT-licensed — free locally with no feature gating.
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
| Cost | Free local; hosted credits | ~$349/yr (Pro) / ~$699/yr (Studio) |
| Modelling paradigm | Parametric feature tree + sketcher | Direct push/pull (no feature history) |
| Precision / tolerances | Exact B-rep (OCCT) | Approximate (face-inference, small-error accumulation) |
| Constraint sketcher | Sketcher v2 | None |
| Sheet metal | Flange + unfold + flat-pattern | Not included |
| Technical drawings | Multi-sheet + GD&T | LayOut (presentation, not engineering standard) |
| IFC export | IFC Tier 2 import | IFC export (Studio) |
| PCB / electronics | In-box | Not applicable |
| Chat / LLM editing | Chat-native | None |
| Rendering | Basic PBR viewport | V-Ray (Studio), Enscape (plugin) |
| Extension ecosystem | Early-stage | Massive (Extensions Warehouse) |
| Community | Early-stage | Tens of millions of users |
| Open source | Yes (MIT) | No |
| STEP export | Yes | No (DWG / DXF / IFC / KMZ) |

## Both export IFC

SketchUp Studio and Kerf both produce IFC (Industry Foundation Classes) output. IFC is the open standard for building information interchange — a SketchUp model exported to IFC can be consumed by Kerf's IFC Tier 2 import and vice versa. This makes the two tools interoperable in AEC workflows where SketchUp handles the architectural massing and Kerf handles structural or MEP engineering elements.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Trimble SketchUp product pages. Kerf capabilities reflect the current shipped product.*
