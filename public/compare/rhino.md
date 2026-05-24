---
slug: rhino
competitor: "Rhino"
category: jewelry-nurbs
left: kerf
right: rhino
hero_tagline: "NURBS & jewelry CAD — class-leading kernel vs MIT open-core."
reviewed_at: 2026-05-19
order: 1
features:
  # ── D1 NURBS / Geometry / Core CAD ──────────────────────────────────────────
  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: yes
      note: "BlendSrf, NetworkSrf, Patch — class-leading NURBS kernel"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/commands/blendsrf.htm"
    kerf:
      status: yes
      note: "blend_srf, network_srf (Gordon), patch_srf_fit all wired as feature ops"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py"

  - domain: D1
    feature: "Surface continuity matching (G0–G3)"
    competitor:
      status: yes
      note: "MatchSrf G0/G1/G2/G3; Sweep2/BlendSrf continuity options"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/commands/blendsrf.htm"
    kerf:
      status: yes
      note: "match_surface_edge_tool G0–G3 + blend_srf_g3 + continuity audit"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/match_srf.py"

  - domain: D1
    feature: "Sweep (1 & 2 rail)"
    competitor:
      status: yes
      note: "Sweep1 and Sweep2 with continuity options"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/commands/sweep2.htm"
    kerf:
      status: yes
      note: "BRepOffsetAPI_MakePipeShell; 1- and 2-rail wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"

  - domain: D1
    feature: "Loft"
    competitor:
      status: yes
      note: "Loft with normal, loose, tight, straight options"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/seealso/sak_surface.htm"
    kerf:
      status: yes
      note: "Loft + guide-rail overload (ThruSections.AddWire), ruled/closed/symmetric"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/feature_loft.py"

  - domain: D1
    feature: "Surface patch from curves/points"
    competitor:
      status: yes
      note: "Patch command — surface through curves, meshes, point clouds"
      source: "https://docs.mcneel.com/rhino/mac/help/en-us/commands/patch.htm"
    kerf:
      status: yes
      note: "patch_srf_fit — least-squares fit through curves/points; wired op"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/patch_srf.py"

  - domain: D1
    feature: "SubD modelling with creases"
    competitor:
      status: yes
      note: "Catmull-Clark SubD with crease/smooth/corner/dart vertices (Rhino 8)"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/seealso/sak_subd.htm"
    kerf:
      status: yes
      note: "SubD authoring with creases; quad remesh"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/quad_remesh.py"

  - domain: D1
    feature: "Mesh repair / ShrinkWrap"
    competitor:
      status: yes
      note: "ShrinkWrap (Rhino 8) + MeshRepair panel"
      source: "http://docs.mcneel.com/rhino/8/help/en-us/commands/shrinkwrap.htm"
    kerf:
      status: partial
      note: "mesh_repair (fill_holes/manifold), retopo_snap, mesh_to_nurbs; no SDF-envelope ShrinkWrap"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/mesh_repair.py"

  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: partial
      note: "Rhino Constraints (Rhino 9 feature); history-based — not full solver"
      source: "https://docs.mcneel.com/rhino/9/help/en-us/commands/constraints.htm"
    kerf:
      status: yes
      note: "PlaneGCS WASM solver; all major geo+dim constraints"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/sketch.py"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: partial
      note: "Via Grasshopper or direct NURBS modeling; no parametric feature tree"
      source: "https://www.rhino3d.com/features/developer/scripting/"
    kerf:
      status: yes
      note: "OCCT feature tree — pad/pocket/revolve wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py"

  - domain: D1
    feature: "Fillet / chamfer (constant)"
    competitor:
      status: yes
      note: "FilletEdge, ChamferEdge on NURBS and SubD"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/toolbarmap/surface_tools_toolbar.htm"
    kerf:
      status: yes
      note: "Constant and variable-radius fillet wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py"

  - domain: D1
    feature: "Boolean operations (B-rep)"
    competitor:
      status: yes
      note: "BooleanUnion, BooleanDifference, BooleanIntersection"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/seealso/sak_surface.htm"
    kerf:
      status: yes
      note: "OCCT general NURBS booleans; no graceful fuzzy heal"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/occ_helpers.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: partial
      note: "Via Grasshopper constraints; no native parametric assembly system"
      source: "https://www.rhino3d.com/features/developer/scripting/"
    kerf:
      status: yes
      note: "Full joint system — rigid/revolute/slider/cam/gear/pin-slot"
      evidence: "packages/kerf-mates/src/kerf_mates/joints.py"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Layout + Make2D + Dim commands; annotation and title blocks"
      source: "http://docs.mcneel.com/rhino/8/help/en-us/commands/layout.htm"
    kerf:
      status: yes
      note: "Multi-sheet drawings with HLR projection + auto-dimension"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/drawings/auto_dimension.py"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: no
      note: "No native sheet-metal workspace; requires plugins"
      source: "https://www.food4rhino.com/en/browse?query=sheet+metal"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF (K-factor)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: partial
      note: "Via Grasshopper parameters; no native config manager"
      source: "https://developer.rhino3d.com/guides/grasshopper/"
    kerf:
      status: yes
      note: "Engine + ConfigurationsPanel wired in Editor.jsx"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py"

  - domain: D1
    feature: "Direct edit (push-pull)"
    competitor:
      status: yes
      note: "Direct mesh/SubD push-pull and NURBS control-point editing"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/seealso/sak_subd.htm"
    kerf:
      status: yes
      note: "push_pull (planar + curved), move_face, delete_face wired as ops"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/direct_edit.py"

  - domain: D1
    feature: "Surface analysis (zebra / curvature combs)"
    competitor:
      status: yes
      note: "Zebra, EMap, CurvatureAnalysis, Draft built-in"
      source: "http://docs.mcneel.com/rhino/8/help/en-us/commands/zebra.htm"
    kerf:
      status: yes
      note: "zebra_analysis, isophote, curvature combs, Gauss/mean, draft-angle ops"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/surface_analysis.py"

  # ── D2 Structural / FEA ──────────────────────────────────────────────────────
  - domain: D2
    feature: "FE — 1D beam / 2D truss (native)"
    competitor:
      status: paid
      note: "Via Karamba3D plugin (paid) on Food4Rhino"
      source: "https://www.food4rhino.com/en/app/karamba3d"
    kerf:
      status: yes
      note: "Hermite beam validated vs Roark (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/linear_static.py"

  - domain: D2
    feature: "FE — plate / shell (native)"
    competitor:
      status: paid
      note: "Shell analysis via Karamba3D plugin (paid)"
      source: "https://www.food4rhino.com/en/app/karamba3d"
    kerf:
      status: yes
      note: "MITC4 plate; 1.29% error vs Timoshenko (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/plate.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "No native steel code check; Grasshopper structural plugins only"
      source: "https://www.food4rhino.com/en/app/karamba3d"
    kerf:
      status: yes
      note: "Full Ch.E/F/H + 50-section catalog (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  # ── D3 Machine elements ───────────────────────────────────────────────────────
  - domain: D3
    feature: "Spur/helical gear rating (AGMA 2001-D04)"
    competitor:
      status: no
      note: "No native gear-strength calculator; Grasshopper geometry only"
      source: "https://www.rhino3d.com/features/developer/scripting/"
    kerf:
      status: yes
      note: "AGMA + ISO 6336 Method B (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gears.py"

  - domain: D3
    feature: "Bearings — ISO 281 L10"
    competitor:
      status: no
      note: "No native bearing life calculator"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "ISO 281 + ISO/TS 16281 aISO modified life (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  # ── D5 Aero / marine / space ──────────────────────────────────────────────────
  - domain: D5
    feature: "Naval hydrostatics + GZ stability (IMO)"
    competitor:
      status: no
      note: "NURBS hull modelling only; no hydrostatics engine"
      source: "https://www.rhino3d.com/en/for/"
    kerf:
      status: yes
      note: "Naval hydrostatics + GZ + IMO stability wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/mooring/lines.py"

  # ── D7 Manufacturing / CAM ────────────────────────────────────────────────────
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: paid
      note: "Via RhinoCAM plugin (paid, MecSoft)"
      source: "https://www.food4rhino.com/en/app/rhinocam"
    kerf:
      status: yes
      note: "3-axis CAM; CAMView wired in UI"
      evidence: "packages/kerf-cam/src/kerf_cam/worker.py"

  - domain: D7
    feature: "5-axis (kinematics + posts)"
    competitor:
      status: paid
      note: "RhinoCAM 5-axis module (paid, MecSoft)"
      source: "https://mecsoft.com/products/rhinocam/rhinocammill/"
    kerf:
      status: partial
      note: "5-axis 3+2 engine solid; no UI panel"
      evidence: "packages/kerf-cam/src/kerf_cam/five_axis/indexed_3_2.py"

  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC)"
    competitor:
      status: paid
      note: "Via RhinoCAM post-processor library (paid)"
      source: "https://mecsoft.com/products/rhinocam/"
    kerf:
      status: yes
      note: "Fanuc/GRBL/LinuxCNC/Mach3 post; no G41/42 cutter-comp"
      evidence: "packages/kerf-cam/src/kerf_cam/posts/fanuc_3x.py"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: paid
      note: "RhinoCAM-NEST module (paid, MecSoft)"
      source: "https://mecsoft.com/products/rhinocam/rhinocamnest/"
    kerf:
      status: yes
      note: "Minkowski NFP + bottom-left fill; 57.6% L-shape util"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/weldline.py"

  - domain: D7
    feature: "Moldflow / fill sim"
    competitor:
      status: no
      note: "No native injection moulding simulation"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "Hele-Shaw front + weld-line + air-trap detection (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/weldline.py"

  # ── D8 Civil / infrastructure / geo ──────────────────────────────────────────
  - domain: D8
    feature: "Landscape (drainage/grading/planting)"
    competitor:
      status: paid
      note: "Via Lands Design / RhinoLands plugin (paid)"
      source: "https://www.food4rhino.com/en/app/rhinolands-lands-design-6"
    kerf:
      status: partial
      note: "Grading + drainage + planting engines (backend only)"
      evidence: "packages/kerf-landscape/src/kerf_landscape/planting.py"

  # ── D12 Optics / acoustics ────────────────────────────────────────────────────
  - domain: D12
    feature: "Paraxial ABCD ray transfer"
    competitor:
      status: no
      note: "No native optics engine; NURBS geometry modelling only"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "Paraxial ABCD ray transfer (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/ray_transfer.py"

  - domain: D12
    feature: "Gaussian beam propagation (M², q-param)"
    competitor:
      status: no
      note: "No native Gaussian beam propagation"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "Complex-q + ABCD + M² + fibre coupling (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/gaussian.py"

  - domain: D12
    feature: "Non-sequential ray tracing (stray light)"
    competitor:
      status: no
      note: "No native ray-tracing optics engine"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "Fresnel-split traversal + ghost detection (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/nonsequential.py"

  # ── D13 Verticals ─────────────────────────────────────────────────────────────
  - domain: D13
    feature: "Jewelry (41 modules)"
    competitor:
      status: paid
      note: "MatrixGold / RhinoGold (paid plugins, Rhino base required)"
      source: "https://www.food4rhino.com/en/app/matrixgoldr"
    kerf:
      status: yes
      note: "41-module jewelry suite — ring v4, settings v3/v4, gems v2"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/ring.py"

  - domain: D13
    feature: "Ring design (profiles/styles)"
    competitor:
      status: paid
      note: "MatrixGold ring builders and shank library (paid plugin)"
      source: "https://gemvision.com/matrixgold"
    kerf:
      status: yes
      note: "Ring v4 — 13+ profiles + 31 templates"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/ring.py"

  - domain: D13
    feature: "Gemstones / cuts"
    competitor:
      status: paid
      note: "MatrixGold gem library (paid); CrossGems (paid)"
      source: "https://www.food4rhino.com/en/app/crossgems"
    kerf:
      status: yes
      note: "Gemstones v2 — 30 cuts"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/gemstones.py"

  - domain: D13
    feature: "Settings / pavé / channel"
    competitor:
      status: paid
      note: "MatrixGold setting wizards (prong/pavé/channel/halo) — paid"
      source: "https://gemvision.com/matrixgold"
    kerf:
      status: yes
      note: "Settings v3/v4 + gem-seat v2 + pavé wizard"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/settings.py"

  - domain: D13
    feature: "Chain / findings"
    competitor:
      status: paid
      note: "MatrixGold chain builder + findings from supplier catalogs (paid)"
      source: "https://gemvision.com/matrixgold"
    kerf:
      status: yes
      note: "Chain v2 + findings + decorative modules"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/chain.py"

  - domain: D13
    feature: "Casting / wax-mill export"
    competitor:
      status: paid
      note: "MatrixGold full wax-mill paths + STL (paid plugin)"
      source: "https://gemvision.com/matrixgold"
    kerf:
      status: partial
      note: "Casting export + wax-carving plan; no full mill-path"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry/casting_export.py"

  - domain: D13
    feature: "Visual node scripting"
    competitor:
      status: yes
      note: "Grasshopper — industry-standard visual scripting (built-in)"
      source: "https://developer.rhino3d.com/guides/grasshopper/"
    kerf:
      status: no
      note: "No visual node environment; chat + kerf-sdk fill part of the gap"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py"

  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: partial
      note: "VisualARQ plugin (paid) adds BIM; base Rhino is pure NURBS"
      source: "https://www.food4rhino.com/en/app/visualarq"
    kerf:
      status: yes
      note: "Revit-comparable BIM engine + IFC4 viewer"
      evidence: "packages/kerf-bim/src/kerf_bim/family_authoring.py"

  # ── D12 / rendering (maps to D5/D13 in context of Rhino) ─────────────────────
  - domain: D12
    feature: "Photoreal rendering (built-in)"
    competitor:
      status: yes
      note: "Rhino Render (Cycles-based) built in; GPU/CPU path-tracing"
      source: "https://docs.mcneel.com/rhino/8/help/en-us/options/rhino_render.htm"
    kerf:
      status: yes
      note: "Cycles backend + browser path tracer; no caustics"
      evidence: "packages/kerf-render/src/kerf_render/cycles_worker.py"

  - domain: D12
    feature: "Photoreal rendering (advanced plugins)"
    competitor:
      status: paid
      note: "V-Ray for Rhino, Enscape, KeyShot — paid plugins"
      source: "https://www.food4rhino.com/en/app/v-ray-rhino"
    kerf:
      status: partial
      note: "BYO Blender/Cycles; no V-Ray/Enscape integration"
      evidence: "packages/kerf-render/src/kerf_render/cycles_translator.py"

  # ── D14 Cost / materials / LCA ────────────────────────────────────────────────
  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: no
      note: "No native material selection database or Ashby charts"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "200 materials, 14 families, Pareto frontier (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/multi_objective.py"

  - domain: D14
    feature: "LCA (full ISO 14040/44 4 phases)"
    competitor:
      status: no
      note: "No lifecycle assessment engine"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "Full ISO 14040/44 LCA with multi-impact categories (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/phases.py"

  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "No cost estimation engine"
      source: "https://www.rhino3d.com/"
    kerf:
      status: yes
      note: "6 processes, Boothroyd-Dewhurst method (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/db.py"
---

# Kerf vs Rhino

Rhino 8 — with the RhinoGold / Matrix lineage now consolidated into MatrixGold / CrossGems — is the professional reference for jewelry CAD and freeform NURBS design. It is a perpetual one-time licence (about US$995 as of May 2026, not a subscription) with the industry-standard NURBS kernel and Grasshopper. Kerf has a strong, free jewelry foundation and integrated B-rep, electronics, and CAM — but Rhino's NURBS depth, Grasshopper ecosystem, and goldsmith-proven plugins are well ahead today. An honest look at both.

## Where Rhino is strong

- **Class-leading NURBS kernel.** Rhino's surface engine is the industry reference for freeform work — jewelry, industrial design, naval architecture, aerospace — with production-proven G0–G3 continuity tools.
- **Grasshopper visual scripting.** The gold standard for parametric 3D, with thousands of components spanning structural optimisation, pattern generation, and more. Kerf has no equivalent visual node environment as of May 2026.
- **Deeply refined jewelry plugins.** MatrixGold / RhinoGold bring years of goldsmith-driven UX: ring builders, stone-setting and pavé wizards, sizing, wax-mill paths, and supplier catalogs.
- **Perpetual licence, no subscription.** A one-time purchase that does not expire — a genuine ownership advantage over subscription CAD tools.
- **SubD and ShrinkWrap.** Rhino 8's SubD (with creases) and ShrinkWrap give fast organic modelling and mesh-recovery workflows Kerf does not match.
- **Advanced rendering ecosystem.** Built-in Cycles plus V-Ray, Enscape, and KeyShot for photoreal jewelry renders with accurate caustics and gem dispersion.
- **RhinoCommon / Python automation.** rhinoscriptsyntax and RhinoCommon expose essentially every kernel operation for scripting.

## Where Kerf differs

- **MIT open-core, free to use.** Rhino is ~US$995 per seat (as of May 2026) and the jewelry plugins add more. Kerf's full jewelry workflow — ring v4, settings v3/v4, gemstones v2, chain v2, 31 templates — is MIT-licensed and free locally.
- **Chat-native workflow.** Describe a change in plain language and the LLM edits the feature tree / JSCAD source with doc-search backing — no visual programming required.
- **Integrated B-rep, electronics, drawings.** An OCCT parametric feature tree, a full EDA stack, multi-sheet drawings, and ASME Y14.5 GD&T are in the same workspace — disciplines Rhino needs separate plugins or tools for.
- **Hosted option or local pip install.** Sign up and design in the browser, or `pip install kerf` locally — no platform-specific installer, no licence dongle.
- **CAM built in.** 3-axis CAM with a tool database and 5-axis 3+2 ship in-box, where Rhino relies on the RhinoCAM plugin.
- **kerf-sdk Python scripting.** Automate jewelry templates and feature trees from any Python script over HTTP/JSON-RPC on your own machine.

## Honest gaps — where Kerf is behind today

- **NURBS surfacing is younger.** blend/network/patch/match-surface, G3 blends, sweep1/2, trim-by-curve, zebra/isophote/curvature-comb analysis and a Class-A continuity harness now ship as wired ops — but Rhino's kernel is decades more battle-tested across edge cases and tolerances, and its freeform UX is far ahead.
- **No Grasshopper equivalent.** Kerf has no visual parametric environment; chat + the Python SDK fill part of that space but not all of it.
- **SubD UX is newer.** Kerf ships SubD authoring with creases, poke/extrude-along, sculpt brushes, multires and SubD-to-NURBS conversion, but Rhino 8's SubD tools are more mature and deeply integrated with the NURBS surfacing workflow.
- **Render quality is narrower.** Kerf's Cycles backend and in-browser path tracer provide photoreal output, but Rhino's plugin ecosystem (V-Ray, Enscape, KeyShot) provides caustics, accurate gem dispersion, and archviz lighting quality that Kerf's render path does not match today.
- **Jewelry plugin depth.** MatrixGold / RhinoGold have supplier catalogs, wax-path generation, and sizing refinements Kerf is still building toward.
- **Smaller community.** Rhino has decades of training, forums, and Food4Rhino plugins; Kerf's ecosystem is early-stage.

## Side by side

| Feature | Rhino | Kerf |
|---|---|---|
| License | ⚠️ Proprietary; perpetual one-time buy | ✅ MIT open-core |
| Cost | ⚠️ ~US$995 full / ~$595 upgrade; +plugin cost (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Subscription | ✅ Perpetual licence, no renewal | ✅ No seat subscription |
| Platform | ⚠️ Windows + macOS desktop | ✅ Browser + single-binary local |
| NURBS surfacing | ✅ Class-leading kernel (G0–G3) | ✅ blend/network/patch/match-srf, G3 blends, sweep1/2 (younger kernel) |
| Surface analysis | ✅ Zebra / EMap / curvature | ✅ Zebra, isophote, curvature combs, Class-A harness |
| SubD modelling | ✅ SubD with creases (Rhino 8) | ✅ SubD authoring, poke/extrude/sculpt/multires, SubD→NURBS |
| Parametric solids (B-rep) | ⚠️ Via Grasshopper / plugins | ✅ OCCT feature tree — pad/pocket/revolve/loft |
| Mesh repair / ShrinkWrap | ✅ ShrinkWrap, mesh tools | ⚠️ fill-holes/manifold + retopo + mesh→NURBS; no SDF-envelope ShrinkWrap |
| Visual node scripting | ✅ Grasshopper — industry standard | ❌ No visual node environment |
| Plugin marketplace | ✅ Thousands of GH components / Food4Rhino | ⚠️ Plugin API early-stage |
| Python / scripting | ✅ rhinoscriptsyntax / RhinoCommon | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| Ring design | ✅ MatrixGold / RhinoGold ring builders | ✅ Ring v4 + 31-template library |
| Gemstones / cuts | ✅ Extensive gem libraries | ✅ Gemstones v2 — 30 cuts |
| Settings / pavé / channel | ✅ Mature stone-setting wizards | ✅ Settings v3/v4 + gem-seat v2 |
| Chain / findings | ✅ Dedicated chain + findings tools | ✅ Chain v2 + findings + decorative |
| Casting / wax-mill export | ✅ STL + wax-mill paths, supplier catalogs | ⚠️ Casting export; no supplier catalogs / wax paths |
| Photoreal rendering | ✅ Cycles + V-Ray/Enscape/KeyShot; caustics | ⚠️ Cycles backend + browser path tracer (no caustics) |
| 2D drawings / GD&T | ⚠️ Layout + annotation plugins | ✅ Multi-sheet drawings + ASME Y14.5 GD&T |
| CNC CAM | ⚠️ Via RhinoCAM plugin | ✅ 3-axis CAM + tool DB; 5-axis 3+2 |
| Electronics | ❌ Separate tool required | ✅ Full EDA stack in same workspace |
| Chat / LLM editing | ❌ No LLM editing we're aware of (as of May 2026) | ✅ Chat-native — edits source per turn |
| Hosted / cloud | ❌ Desktop only (no hosted option we're aware of, as of May 2026) | ✅ Hosted SaaS + local install |
