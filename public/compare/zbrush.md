---
slug: zbrush
competitor: "Maxon ZBrush"
category: dcc
left: kerf
right: zbrush
hero_tagline: "ZBrush sculpts the organic world in polygons — Kerf models the engineered world in exact B-rep."
reviewed_at: 2026-05-24
features:
  - domain: D1
    feature: "Geometry & core CAD — B-rep solid modelling"
    competitor:
      status: no
      note: "Polygon mesh (DynaMesh, subdivision) — no B-rep kernel, no exact surfaces"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: yes
      note: "OCCT B-rep kernel; pad/pocket/revolve/fillet/sweep/loft wired"
      evidence: "packages/kerf-occt/"

  - domain: D1
    feature: "Geometry & core CAD — constraint sketcher"
    competitor:
      status: no
      note: "No parametric sketcher; brush-based sculpting only"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: yes
      note: "PlaneGCS WASM sketcher with geometric + dimensional constraints"
      evidence: "packages/kerf-sketcher/"

  - domain: D1
    feature: "Geometry & core CAD — parametric feature history"
    competitor:
      status: no
      note: "Non-parametric; changes require manual re-sculpting"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: yes
      note: "Persistent feature DAG; upstream edits regenerate downstream geometry"
      evidence: "packages/kerf-modeller/"

  - domain: D1
    feature: "Geometry & core CAD — organic mesh sculpting"
    competitor:
      status: yes
      note: "Industry gold standard: DynaMesh, ZRemesher, ZSpheres, 30+ brushes at 10M+ poly"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: no
      note: "No sculpt mode; mesh tools + quad remesh only"
      evidence: "packages/kerf-mesh/"

  - domain: D1
    feature: "Geometry & core CAD — STEP / IGES B-rep export"
    competitor:
      status: no
      note: "Exports OBJ / STL / GoZ mesh only; no B-rep STEP writer"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: yes
      note: "STEP, IGES, 3DM B-rep round-trip via OCCT"
      evidence: "packages/kerf-io/"

  - domain: D2
    feature: "Structural / FEA — finite element analysis"
    competitor:
      status: no
      note: "No FEA or structural analysis capability"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: partial
      note: "Deep backend engines (AISC/ACI/NDS/EC codes, FEM beam/plate/shell); minimal UI"
      evidence: "packages/kerf-structural/"

  - domain: D3
    feature: "Machine elements — gear / bearing / fastener sizing"
    competitor:
      status: no
      note: "No machine-element calculators"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: partial
      note: "Shigley/AGMA/ISO/VDI grade engines; entirely backend, no UI panel"
      evidence: "packages/kerf-mechanical/"

  - domain: D4
    feature: "Thermal / fluid / HVAC — simulation"
    competitor:
      status: no
      note: "No thermal or fluid simulation"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: partial
      note: "ASHRAE psychrometrics, LMTD/ε-NTU HX, Hardy-Cross pipe network, OpenFOAM bridge; backend"
      evidence: "packages/kerf-thermal/"

  - domain: D6
    feature: "Electronics / EDA / silicon — PCB and schematic"
    competitor:
      status: no
      note: "No EDA capability; sculpting-only tool"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: partial
      note: "KiCad-round-trip viewer, ngspice SPICE, DRC overlay wired; interactive routing not yet"
      evidence: "packages/kerf-ecad/"

  - domain: D7
    feature: "Manufacturing / CAM — 3D print output"
    competitor:
      status: yes
      note: "Direct STL / OBJ / 3MF mesh export; primary workflow for resin wax printing"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: yes
      note: "STEP → mesh pipeline + FDM slicing via Cura (PrintSliceView wired)"
      evidence: "packages/kerf-cam/"

  - domain: D7
    feature: "Manufacturing / CAM — CNC / G-code output"
    competitor:
      status: no
      note: "Not designed for CNC; no G-code post-processor"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: yes
      note: "3-axis CAM wired (CAMView); Fanuc/GRBL/LinuxCNC posts"
      evidence: "packages/kerf-cam/"

  - domain: D7
    feature: "Manufacturing / CAM — retopology / mesh cleanup"
    competitor:
      status: yes
      note: "ZRemesher automatic retopology; Decimation Master; manual retopo tools"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: partial
      note: "quad/isotropic remesh + retopo_snap + decimate ops (ZRemesher-class); no interactive brush UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/mesh_implicit_tools.py"

  - domain: D13
    feature: "Verticals — jewelry sculpting / organic concept"
    competitor:
      status: yes
      note: "DynaMesh + ZRemesher sculpt; standard tool for organic ring shanks and bespoke settings"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: partial
      note: "41 parametric modules + SubD authoring/sculpt_brush; not DynaMesh-grade for free organic forms"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/subd_tools.py"

  - domain: D13
    feature: "Verticals — jewelry parametric configurator"
    competitor:
      status: no
      note: "No parametric ring/gemstone/setting modules; organic mesh sculpting only"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: yes
      note: "41-module jewelry suite: ring v4, gemstone v2, settings v3/v4, chain v2, casting export"
      evidence: "packages/kerf-jewelry/"

  - domain: D13
    feature: "Verticals — dental anatomic sculpting"
    competitor:
      status: yes
      note: "Used professionally for anatomic crown/coping sculpting; high-poly mesh detail"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: partial
      note: "Dental spotlight exists; crown is placeholder cylinder, not anatomically graded"
      evidence: "packages/kerf-dental/"

  - domain: D13
    feature: "Verticals — character / creature / film VFX"
    competitor:
      status: yes
      note: "Industry standard for character sculpting, FiberMesh, polypaint, ZSpheres, NPR render"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: no
      note: "No character sculpting, rigging, or film VFX tooling — out of scope"
      evidence: ""

  - domain: D13
    feature: "Verticals — texture / polypaint / displacement"
    competitor:
      status: yes
      note: "Polypaint, UV Master, displacement / normal map baking, fiber textures"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: no
      note: "No polypaint or displacement-map authoring"
      evidence: ""

  - domain: D13
    feature: "Verticals — hard-surface modelling (ZModeler)"
    competitor:
      status: yes
      note: "ZModeler brush for hard-surface polygon work; used for concept vehicles and props"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: yes
      note: "Exact B-rep hard-surface via OCCT feature tree — dimensionally accurate"
      evidence: "packages/kerf-occt/"

  - domain: D13
    feature: "Verticals — rendering quality"
    competitor:
      status: yes
      note: "BPR renderer + KeyShot bridge; NPR rendering, ambient occlusion, fibres"
      source: "https://docs.maxon.net/r/ZBrush/2024/en-US/"
    kerf:
      status: partial
      note: "HeroShot.js PBR viewport (HDRI + ACES + bloom); no path-traced renderer"
      evidence: "src/components/heroShot.js"

  - domain: D14
    feature: "Cost / materials / LCA — material selection and costing"
    competitor:
      status: no
      note: "No material database, should-cost, or LCA tooling"
      source: "https://www.maxon.net/zbrush/features/"
    kerf:
      status: partial
      note: "Ashby material selector (200 materials), should-cost (6 processes), full LCA; backend/agent only"
      evidence: "packages/kerf-materials/"
---

# Kerf vs Pixologic ZBrush

ZBrush (now owned by Maxon) is the definitive tool for high-resolution organic digital sculpting. Character artists, concept sculptors, creature designers, and jewellery prototypers use it to produce polygon meshes at multi-million-polygon resolutions with clay-like brush interaction. It is a creative tool first — precision dimensioning is not its goal. Kerf is an engineering CAD tool first — exact geometry, parametric history, and downstream fabrication are its goals. These tools occupy different niches, but they intersect for product designers, jewellery designers, and anyone moving between organic concepting and manufacturable output.

## Where they converge

Both ZBrush and Kerf are used in the jewellery industry. ZBrush is widely used for organic ring shanks, creature-inspired settings, and bespoke sculpture-based pieces that would be impossible to construct from parametric primitives. Kerf ships a 40-module jewellery suite (ring, gemstones, settings, chain, findings, casting export) that covers the more structured, parametric end of the same market. Jewellery designers often use both: ZBrush for organic concept, Kerf for dimensional accuracy and manufacturing output.

Both tools can output geometry for 3D printing — ZBrush via STL/OBJ mesh export, Kerf via STEP-to-mesh pipeline. Both acknowledge that jewellery casting requires geometry that closes cleanly (no holes, correct wall thickness) and both have workflows oriented around that constraint.

## Where Kerf wins

- **Exact B-rep, not mesh.** Kerf geometry is mathematically exact — surfaces are defined by splines and analytic primitives, not polygon approximations. For jewellery, this means a ring shank is truly round, a gemstone seat is exactly the right depth, and wall thickness is a parameter, not a guess at mesh resolution.
- **Parametric history.** Change a ring size, and every downstream feature (seat depth, prong height, shank width at the gallery) updates automatically. ZBrush is non-parametric: changes require manual re-sculpting.
- **Engineering fabrication output.** Kerf produces STEP, IGES, DXF, Gerber, IPC-2581 — formats that CNC machines, PCB fabs, and CAM systems consume natively. ZBrush produces mesh formats (OBJ, STL, GoZ) suited for 3D printing and rendering, not precision CNC machining.
- **Multi-domain.** If your product has electronics — a smart ring, a connected device, a wearable — Kerf covers the PCB schematic, layout, and pre-compliance simulation in the same workspace. ZBrush is sculpting only.
- **MIT open-core, no subscription.** ZBrush moved from a perpetual model to a subscription (Maxon One or ZBrush standalone ~$39.99/mo as of May 2026). Kerf is MIT-licensed — free locally.

## Where ZBrush wins

- **Organic sculpting quality.** ZBrush's brush-based sculpting at 10M+ polygon resolution, with DynaMesh, ZRemesher, and multi-resolution subdivision, produces organic surfaces that parametric CAD tools simply cannot replicate. Skin pores, creature scales, and flowing organic forms are ZBrush's domain.
- **Sculptural speed.** A concept sculptor can block out a figure in ZBrush in minutes using brushes and DynaMesh. The same shape in parametric CAD would require extraordinary effort and would not capture the same organic quality.
- **Texture and surface detail.** ZBrush projects painted texture, displacement maps, and micro-detail onto geometry in ways that are invisible to engineering CAD. For rendering and 3D printing with visible surface detail, ZBrush is unmatched.
- **Established creative ecosystem.** ZBrush has the largest community of digital sculptors in the world, decades of tutorials, and deep integration with rendering tools (KeyShot, Marvelous Designer, Substance).
- **Fibermesh / cloth / hair.** Organic material simulation for fibres, cloth, and hair for character/creature work — entirely outside the scope of engineering CAD.

## Feature matrix

| Feature | Kerf | ZBrush (Maxon) |
|---|---|---|
| License | MIT open-core | Proprietary subscription (~$39.99/mo, May 2026) |
| Geometry type | Exact B-rep (NURBS/OCCT) | Polygon mesh (DynaMesh, subdivision) |
| Parametric history | Feature DAG (fully parametric) | Non-parametric (brush-based) |
| Organic sculpting | Not designed for this | Industry gold standard |
| Jewellery tooling | 40-module suite (ring/gem/setting/chain) | Organic/sculptural pieces (no parametric modules) |
| Precision dimensioning | Yes (exact geometry) | Limited (mesh approximations) |
| STEP export | Yes | No (OBJ / STL / GoZ) |
| 3D print output | Via STEP → mesh pipeline | Direct STL/OBJ/3MF export |
| PCB / electronics | In-box | Not applicable |
| Chat / LLM editing | Chat-native | No LLM editing we're aware of (as of May 2026) |
| FEM / simulation | Not yet | Not applicable |
| CAM / CNC output | DXF / STEP for CNC | Not designed for CNC |
| Rendering | Basic PBR viewport | KeyShot bridge, ZBrush BPR |
| Community / tutorials | Early-stage | Massive (largest sculpting community) |
| Open source | Yes (MIT) | No |

## Both produce 3D-printable output

ZBrush exports STL and OBJ meshes that go directly to wax printers and FDM printers. Kerf exports STEP geometry that converts cleanly to STL for the same workflow. Jewellery designers who concept in ZBrush and refine dimensions in Kerf can use either tool's output for the same casting workflow — the handoff is STL or STEP.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Maxon/ZBrush product pages. Kerf capabilities reflect the current shipped product.*
