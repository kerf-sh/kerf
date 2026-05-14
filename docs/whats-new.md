# What's New

Recent features shipped to Kerf. See [ROADMAP.md](https://github.com/imranp/kerf/blob/main/ROADMAP.md) for the full list and status of every item.

## Sprint — May 2026 (Massive Feature Wave)

### Sketcher / Mechanical
6 new constraints (horizontal/vertical distance, symmetric, block, equal angle, parallel). Arc/circle edge projection for external geometry. Multi-loop holes in extrude/pocket. 3D backdrop overlay. Carbon-copy sketches with validation. [sketch.md](../packages/kerf-chat/llm_docs/sketch.md)

### Features — PartDesign / FreeCAD Parity
Helix (variable-pitch), tapered Draft, Mirror, Multi-Transform, and Rib features shipped. ~10 new curve operations (offset, extend, blend, trim, intersect, project, section, split, isotrim, swap). [feature.md](../packages/kerf-chat/llm_docs/feature.md) · [curve_ops.md](../packages/kerf-chat/llm_docs/curve_ops.md)

### Surface Modeling — Rhino Parity
SubD (Catmull-Clark subdivision surfaces). Full 3DM import/export. Mesh tools: remesh, decimate, smooth, repair, fill-holes, surface-from-points. Render-quality output via Blender Cycles. Parametric `.graph` (Grasshopper-equivalent). [subd.md](../packages/kerf-imports/llm_docs/subd.md) · [import_3dm.md](../packages/kerf-imports/llm_docs/import_3dm.md) · [mesh.md](../packages/kerf-imports/llm_docs/mesh.md) · [render.md](../packages/kerf-render/llm_docs/render.md) · [graph.md](../packages/kerf-imports/llm_docs/graph.md)

### Drawings — Draft Workbench
Hatch patterns, leader lines, rich text, and dimension chains — full drafting completeness. Draft workbench (2D CAD) for technical drawings. [drawing.md](../packages/kerf-chat/llm_docs/drawing.md) · [draft.md](../packages/kerf-imports/llm_docs/draft.md)

### Architecture — Revit Parity
IFC compiler (`POST /compile-ifc` → IFC4 via IfcOpenShell). `.family.json` parametric components, `.schedule.json` query DSL, `.view.json` saved views, `.sheet.json` print layouts. Categories + hosted references, type vs instance params, phasing + view filters. Stairs, railings, MEP routing (`.duct`/`.pipe`/`.conduit`), curtain wall, sheet revisions. [bim.md](../packages/kerf-bim/llm_docs/bim.md) · [family.md](../packages/kerf-bim/llm_docs/family.md) · [schedule.md](../packages/kerf-bim/llm_docs/schedule.md) · [view.md](../packages/kerf-bim/llm_docs/view.md) · [sheet.md](../packages/kerf-bim/llm_docs/sheet.md) · [stairs.md](../packages/kerf-bim/llm_docs/stairs.md) · [railings.md](../packages/kerf-bim/llm_docs/railings.md) · [mep.md](../packages/kerf-bim/llm_docs/mep.md) · [curtain_wall.md](../packages/kerf-bim/llm_docs/curtain_wall.md) · [sheet_revisions.md](../packages/kerf-imports/llm_docs/sheet_revisions.md)

### Electronics — KiCad Parity
Manual trace routing, copper pours/ground planes, full layer stack. PCB DRC, ERC (electrical rules check), net classes. Length tuning + diff-pair match, via stitching + teardrops. Push-pull (shove) router. Hierarchical schematics, buses + differential pairs. Per-pad mask/paste overrides. [circuit.md](../packages/kerf-chat/llm_docs/circuit.md) · [pcb_layers.md](../packages/kerf-chat/llm_docs/pcb_layers.md) · [pcb_drc.md](../packages/kerf-chat/llm_docs/pcb_drc.md) · [erc.md](../packages/kerf-electronics/llm_docs/erc.md) · [net_classes.md](../packages/kerf-electronics/llm_docs/net_classes.md) · [length_tuning.md](../packages/kerf-electronics/llm_docs/length_tuning.md) · [via_stitching.md](../packages/kerf-electronics/llm_docs/via_stitching.md) · [shove_router.md](../packages/kerf-electronics/llm_docs/shove_router.md) · [hier_schematic.md](../packages/kerf-electronics/llm_docs/hier_schematic.md) · [buses.md](../packages/kerf-electronics/llm_docs/buses.md) · [pad_overrides.md](../packages/kerf-electronics/llm_docs/pad_overrides.md)

### Workshop / Library / Cloud
Workshop + Library endpoints ported. Cloud git → S3 Storer (stateless serverless). Large-file `.step-ref` Phase 1 (JSON pointer + object storage). GitHub OAuth. AES-GCM encrypt utility. [library.md](../packages/kerf-chat/llm_docs/library.md) · [derived_cache.md](../packages/kerf-chat/llm_docs/derived_cache.md)

### Inspection / Misc
Model comparison tool. Distributor catalog ported. Configurable layers + display modes. [inspection.md](../packages/kerf-imports/llm_docs/inspection.md) · [distributors.md](../packages/kerf-chat/llm_docs/distributors.md) · [workspace.md](../packages/kerf-chat/llm_docs/workspace.md)
