# Importing from external CAD tools

Kerf supports first-cut import from popular CAD/EDA tools. The goal is a working starting point in a native Kerf file type — not a lossless round-trip. You iterate from there via chat, script, or direct edit.

All imports produce native Kerf file types that the LLM assistant can work with immediately. Large binary assets (STEP models, STL meshes) are handled via the `.step-ref` pointer system so they don't bloat git history.

## OpenSCAD

**Status: available (browser-side)**

OpenSCAD is the easiest and fastest import path — it's a sister CSG language to JSCAD, so translation is clean and runs entirely in the browser (no server dependency).

**How to import:**
- In the file tree, click "+ New" → "Import OpenSCAD…"
- Select a `.scad` file from your machine
- A `.jscad` file is created in the project, preserving the parametric model

**What translates in v1:**
- Primitives: `cube`, `sphere`, `cylinder`
- Transforms: `translate`, `rotate` (degrees converted to radians), `scale`
- Booleans: `union`, `difference`, `intersection`
- Variables and named constants
- `module` and `function` definitions
- `for` loops with range expressions

**What doesn't translate in v1:**
- `surface()` — mesh from height-map
- Customizer GUI hints (`// [min:max:step]` comments)
- `include<>` / `use<>` — external file references
- `import()` of STL/DXF
- Advanced built-ins: `hull()`, `minkowski()`, `offset()`, `projection()`

**Escape hatch:** For exotic features, render to STL in OpenSCAD first, then import the mesh into Kerf as a `.step` file (lossy — parametric model is not preserved).

## KiCad

**Status: in progress (pyworker-backed)**

KiCad import translates schematic and PCB files into Kerf's native `.circuit.tsx` format (tscircuit).

**How to import:**
- Upload a `.kicad_sch`, `.kicad_pcb`, or zipped KiCad project
- The cloud `pyworker` service runs the translation
- A `.circuit.tsx` file is created in the project

**What translates in Tier 1:**
- Schematic components → tscircuit primitives (`<resistor>`, `<capacitor>`, `<chip>`, etc.)
- Net connections → `<trace>` elements
- Common footprints via a translation table (~100 most common)
- Schematic and PCB placement (x/y coordinates)

**What doesn't translate in Tier 1:**
- Hierarchical schematic sheets (flattened in v1)
- Lossless round-trip or export back to KiCad
- Full layout fidelity (differential pairs, layer stack-ups, custom design rules)
- ERC/DRC rule preservation
- Uncommon footprints (become `<chip footprint="kicad:lib:name">` placeholders)

**Note:** Requires the cloud pyworker service. Local-install users can run `kerf-pyworker` themselves.

## FreeCAD

**Status: not yet available**

FreeCAD import is planned but not yet implemented. It's the most complex of the three imports due to FreeCAD's rich data model.

When available, the plan is:

**Tier 1 — Part + PartDesign features:**
- Maps FreeCAD features to Kerf `.feature` + `.sketch` files
- Both Kerf and FreeCAD use OpenCascade under the hood, so BRep geometry transfers without re-meshing
- Common operations: Pad, Pocket, Revolve, Hole, Fillet, Chamfer, Shell, Sweep, Loft, Mirror, patterns

**Tier 2 — Richer fidelity:**
- Sketcher constraints → Kerf sketch constraints
- FreeCAD Spreadsheet → Kerf `.equations` file
- TechDraw drawings → Kerf drawing files
- Materials library mapping

Watch the [roadmap](../ROADMAP.md) for updates on FreeCAD import availability.

## General tips

- After any import, open the file and use the chat assistant to refine the result — the LLM can fix translation artifacts conversationally.
- The LLM tool equivalents (`kicad_import_project`, etc.) let scripts and the chat assistant invoke the same import flows programmatically via `kerf-sdk`.
- For files that don't import cleanly, importing the rendered STEP/STL as a mesh is always an option — you lose the parametric model but keep the geometry.
