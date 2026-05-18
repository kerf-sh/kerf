---
slug: zbrush
competitor: Pixologic ZBrush
category: cad-creative
left: kerf
right: zbrush
hero_tagline: "ZBrush sculpts the organic world in polygons — Kerf models the engineered world in exact B-rep."
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
- **MIT open-core, no subscription.** ZBrush moved from a perpetual model to a subscription (Maxon One or ZBrush standalone ~$39.99/mo). Kerf is MIT-licensed — free locally.

## Where ZBrush wins

- **Organic sculpting quality.** ZBrush's brush-based sculpting at 10M+ polygon resolution, with DynaMesh, ZRemesher, and multi-resolution subdivision, produces organic surfaces that parametric CAD tools simply cannot replicate. Skin pores, creature scales, and flowing organic forms are ZBrush's domain.
- **Sculptural speed.** A concept sculptor can block out a figure in ZBrush in minutes using brushes and DynaMesh. The same shape in parametric CAD would require extraordinary effort and would not capture the same organic quality.
- **Texture and surface detail.** ZBrush projects painted texture, displacement maps, and micro-detail onto geometry in ways that are invisible to engineering CAD. For rendering and 3D printing with visible surface detail, ZBrush is unmatched.
- **Established creative ecosystem.** ZBrush has the largest community of digital sculptors in the world, decades of tutorials, and deep integration with rendering tools (KeyShot, Marvelous Designer, Substance).
- **Fibermesh / cloth / hair.** Organic material simulation for fibres, cloth, and hair for character/creature work — entirely outside the scope of engineering CAD.

## Feature matrix

| Feature | Kerf | ZBrush (Maxon) |
|---|---|---|
| License | MIT open-core | Proprietary subscription (~$39.99/mo) |
| Geometry type | Exact B-rep (NURBS/OCCT) | Polygon mesh (DynaMesh, subdivision) |
| Parametric history | Feature DAG (fully parametric) | Non-parametric (brush-based) |
| Organic sculpting | Not designed for this | Industry gold standard |
| Jewellery tooling | 40-module suite (ring/gem/setting/chain) | Organic/sculptural pieces (no parametric modules) |
| Precision dimensioning | Yes (exact geometry) | Limited (mesh approximations) |
| STEP export | Yes | No (OBJ / STL / GoZ) |
| 3D print output | Via STEP → mesh pipeline | Direct STL/OBJ/3MF export |
| PCB / electronics | In-box | Not applicable |
| Chat / LLM editing | Chat-native | None |
| FEM / simulation | Not yet | Not applicable |
| CAM / CNC output | DXF / STEP for CNC | Not designed for CNC |
| Rendering | Basic PBR viewport | KeyShot bridge, ZBrush BPR |
| Community / tutorials | Early-stage | Massive (largest sculpting community) |
| Open source | Yes (MIT) | No |

## Both produce 3D-printable output

ZBrush exports STL and OBJ meshes that go directly to wax printers and FDM printers. Kerf exports STEP geometry that converts cleanly to STL for the same workflow. Jewellery designers who concept in ZBrush and refine dimensions in Kerf can use either tool's output for the same casting workflow — the handoff is STL or STEP.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Maxon/ZBrush product pages. Kerf capabilities reflect the current shipped product.*
