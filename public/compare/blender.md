---
slug: blender
competitor: "Blender"
category: dcc
left: kerf
right: blender
hero_tagline: "World-class mesh / DCC tool — a different category from B-rep CAD."
reviewed_at: 2026-05-19
order: 1
features:
  # D1 — Geometry & core CAD
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: no
      note: "No parametric constraint sketcher; Blender is mesh-only"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "PlaneGCS WASM; geometric + dimensional constraints"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: no
      note: "No parametric feature history; Modifier Stack is non-persistent"
      source: "https://docs.blender.org/manual/en/latest/modeling/modifiers/index.html"
    kerf:
      status: yes
      note: "OCCT feature tree, wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Loft"
    competitor:
      status: no
      note: "Skinning via Skin modifier is mesh-only, no B-rep loft"
      source: "https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/skin.html"
    kerf:
      status: yes
      note: "Guide-rail overload wired (ThruSections.AddWire); ruled/closed/symmetric"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/feature_loft.py"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: no
      note: "Mesh booleans (Boolean modifier) — not B-rep; no tolerance healing"
      source: "https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/booleans.html"
    kerf:
      status: yes
      note: "OCCT B-rep booleans; no graceful failure / fuzzy heal"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: no
      note: "NURBS curve objects only; no NURBS solid surfacing"
      source: "https://docs.blender.org/manual/en/latest/modeling/curves/index.html"
    kerf:
      status: yes
      note: "blend_srf, network_srf (Gordon), patch_srf_fit, match_srf, G3 blends wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: no
      note: "No parametric assembly system or constraint-based mates"
      source: "https://docs.blender.org/manual/en/latest/scene_layout/object/index.html"
    kerf:
      status: yes
      note: "Wired; coincident/concentric/parallel + BOM panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: no
      note: "No technical drawing output; Blender is rendering-only"
      source: "https://docs.blender.org/manual/en/latest/render/index.html"
    kerf:
      status: partial
      note: "Live HLR projection (make2d) + auto-dim; no GD&T-placement UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/make2d.py"

  - domain: D1
    feature: "GD&T on drawings / MBD / PMI"
    competitor:
      status: no
      note: "No GD&T concept; not an engineering tool"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: partial
      note: "Data model only; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: no
      note: "No sheet-metal tooling"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF (K-factor)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D1
    feature: "STEP / IGES B-rep interop"
    competitor:
      status: no
      note: "Exports mesh formats only (glTF, FBX, OBJ); no B-rep STEP writer"
      source: "https://docs.blender.org/manual/en/latest/files/import_export/index.html"
    kerf:
      status: yes
      note: "STEP / IGES / 3DM B-rep round-trip"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: no
      note: "No parametric configuration system"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "Engine complete; no UI panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/configs"

  # D2 — Structural / FEA
  - domain: D2
    feature: "FE — solid (tet/hex)"
    competitor:
      status: no
      note: "Blender has no FEA; physics sims are for animation only"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "CalculiX/Mystran/Z88 bridge (needs binary; backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/calculix_bridge.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "Not an engineering code-compliance tool"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "Full Ch. E/F/H + 50-section catalog (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/steel_beam.py"

  - domain: D2
    feature: "ACI 318-19 concrete"
    competitor:
      status: no
      note: "No structural design code in Blender"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "Flexure/shear/PM/dev-length (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/rc_beam.py"

  - domain: D2
    feature: "Fatigue (S-N, ε-N, rainflow)"
    competitor:
      status: no
      note: "No fatigue analysis; physics is purely visual/animation"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "S-N, ε-N, rainflow counting (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/fatigue_fem.py"

  # D3 — Machine elements
  - domain: D3
    feature: "Spur/helical gear rating (AGMA 2001-D04)"
    competitor:
      status: no
      note: "No machine-element calculators in Blender"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "Full AGMA 2001-D04 rating (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D3
    feature: "Bearings — ISO 281 L10"
    competitor:
      status: no
      note: "No bearing life calculation in Blender"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "ISO 281 L10 + ISO/TS 16281 modified life (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  # D4 — Thermal / fluid / HVAC
  - domain: D4
    feature: "CFD"
    competitor:
      status: no
      note: "Mantaflow is smoke/fluid for animation VFX — not engineering CFD"
      source: "https://docs.blender.org/manual/en/latest/physics/fluid/index.html"
    kerf:
      status: yes
      note: "Real OpenFOAM bridge (needs install; backend)"
      evidence: "packages/kerf-cfd/src/kerf_cfd/openfoam_bridge.py"

  - domain: D4
    feature: "HVAC duct sizing (SMACNA)"
    competitor:
      status: no
      note: "No HVAC engineering calculators"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "SMACNA duct sizing + flat-pattern (backend)"
      evidence: "packages/kerf-hvac/src/kerf_hvac/duct.py"

  - domain: D4
    feature: "Heat exchangers (LMTD + ε-NTU + Bell-Delaware)"
    competitor:
      status: no
      note: "No thermal engineering calculators"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "LMTD + ε-NTU + Bell-Delaware + TEMA (backend)"
      evidence: "packages/kerf-hvac/src/kerf_hvac/sizing.py"

  # D5 — Aero / marine / space
  - domain: D5
    feature: "Airfoil inviscid CL (panel)"
    competitor:
      status: no
      note: "No aerodynamic panel methods"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "2D panel method, wired"
      evidence: "packages/kerf-aero/src/kerf_aero/panel_2d.py"

  - domain: D5
    feature: "Orbital (Kepler, J2/J3, Hohmann)"
    competitor:
      status: no
      note: "No orbital mechanics"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "Kepler + J2/J3 + Hohmann + Lambert, wired"
      evidence: "packages/kerf-aero/src/kerf_aero"

  # D6 — Electronics / EDA / silicon
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: no
      note: "No electronics tooling in Blender"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "KiCad round-trip viewer (read-only)"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: no
      note: "No PCB tooling in Blender"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "PCB viewer wired (read-only); fab: Gerber/ODB++/IPC-2581"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab"

  - domain: D6
    feature: "SPICE"
    competitor:
      status: no
      note: "No circuit simulation"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Real ngspice, wired; binary .raw not parsed"
      evidence: "packages/kerf-electronics/src/kerf_electronics/spice_bridge.py"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No SI analysis"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "IBIS 5.1 parser + Bergeron + PRBS eye (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si/ibis_channel.py"

  # D7 — Manufacturing / CAM
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: no
      note: "No CAM tooling in Blender"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "CAMView wired"
      evidence: "src/components/CAMView.jsx"

  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC/Mach3)"
    competitor:
      status: no
      note: "No G-code output"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Fanuc/GRBL/LinuxCNC/Mach3; no G41/42 cutter-comp"
      evidence: "packages/kerf-cam/src/kerf_cam/gcode_post.py"

  - domain: D7
    feature: "FDM slicing (Cura)"
    competitor:
      status: no
      note: "No built-in slicer; Blender exports STL for external slicers"
      source: "https://docs.blender.org/manual/en/latest/files/import_export/stl.html"
    kerf:
      status: yes
      note: "CuraEngine via PrintSliceView, wired"
      evidence: "src/components/PrintSliceView.jsx"

  - domain: D7
    feature: "Moldflow / fill sim"
    competitor:
      status: no
      note: "No injection-moulding simulation"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Hele-Shaw front tracking + weld-line + air-trap (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/moldflow/flow_front.py"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: no
      note: "No sheet-nesting tooling"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Minkowski-sum NFP + IFP + bottom-left fill (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/nesting/nfp.py"

  # D8 — Civil / infrastructure / geo
  - domain: D8
    feature: "Horizontal+vertical alignment (clothoid, SSD)"
    competitor:
      status: no
      note: "No civil engineering tools"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Clothoid + SSD + corridor templates (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/alignment.py"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/pile/liquefaction)"
    competitor:
      status: no
      note: "No geotechnical calculators"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Full geotech suite + Seed-Idriss liquefaction (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/geotech/liquefaction.py"

  # D9 — Dynamics / controls
  - domain: D9
    feature: "Planar MBD (Lagrange/DAE, Baumgarte)"
    competitor:
      status: no
      note: "Blender rigid-body is Bullet physics for animation, not MBD"
      source: "https://docs.blender.org/manual/en/latest/physics/rigid_body/index.html"
    kerf:
      status: yes
      note: "Lagrange/DAE + Baumgarte stabilisation (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/mbd_2d.py"

  - domain: D9
    feature: "Controls — classical (Routh/Bode/RL/PID tune)"
    competitor:
      status: no
      note: "No controls engineering tools"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Routh/Bode/root-locus/PID (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/controls/pid.py"

  - domain: D9
    feature: "Controls — state-space / LQR / Kalman"
    competitor:
      status: no
      note: "No state-space control in Blender"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Ackermann + LQR (CARE) + Luenberger (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/controls/statespace.py"

  # D10 — Electrical / energy / PLC
  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB/motion)"
    competitor:
      status: no
      note: "No PLC tooling in Blender"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim, wired"
      evidence: "src/components/PLCEditorPanel.jsx"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "No energy engineering calculators"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + global MPPT (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/solarpv/shading.py"

  # D11 — Tolerancing / QA
  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS/MC)"
    competitor:
      status: no
      note: "No GD&T or tolerance analysis"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "WC/RSS/Monte-Carlo (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolstack"

  - domain: D11
    feature: "Process capability (Cpk/Ppk)"
    competitor:
      status: no
      note: "No quality/metrology tooling"
      source: "https://docs.blender.org/manual/en/latest/modeling/index.html"
    kerf:
      status: yes
      note: "Cpk/Ppk + SPC charts (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/spc/charts.py"

  # D12 — Optics / acoustics
  - domain: D12
    feature: "Path-traced renderer (Cycles/EEVEE)"
    competitor:
      status: yes
      note: "Cycles (GPU path tracer) + EEVEE (real-time PBR) — benchmark quality"
      source: "https://www.blender.org/features/rendering/"
    kerf:
      status: partial
      note: "HDRI + ACES + bloom (heroShot.js); no full path tracer"
      evidence: "src/components/HeroShot.jsx"

  - domain: D12
    feature: "Paraxial ABCD ray transfer"
    competitor:
      status: no
      note: "Cycles is rasterisation/path tracing for VFX, not optical engineering"
      source: "https://docs.blender.org/manual/en/latest/render/cycles/index.html"
    kerf:
      status: yes
      note: "Paraxial ABCD ray transfer (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/abcd.py"

  - domain: D12
    feature: "Acoustics (ISO 9613, RT60, weighting, mass-law TL)"
    competitor:
      status: no
      note: "No engineering acoustics calculators"
      source: "https://docs.blender.org/manual/en/latest/physics/index.html"
    kerf:
      status: yes
      note: "ISO 9613 + RT60 + SEA + image-source IR (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/acoustics/wave.py"

  # D13 — Verticals
  - domain: D13
    feature: "Sculpting + dyntopo + multires"
    competitor:
      status: yes
      note: "Full sculpt mode — Dyntopo, Multires, 30+ brushes (benchmark)"
      source: "https://www.blender.org/features/sculpt-paint/"
    kerf:
      status: partial
      note: "sculpt_brush (grab/smooth/inflate) + multires + isotropic remesh; no dyntopo/30+ brushes"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/subd_tools.py"

  - domain: D13
    feature: "Animation / rigging"
    competitor:
      status: yes
      note: "Full skeletal animation, NLA, shape keys, cloth, fluid, particles"
      source: "https://www.blender.org/features/animation/"
    kerf:
      status: no
      note: "No animation or rigging; not planned"
      evidence: "src/components"

  - domain: D13
    feature: "Geometry Nodes (visual node DAG)"
    competitor:
      status: yes
      note: "Mature mesh-centric procedural node graph with simulation nodes"
      source: "https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/index.html"
    kerf:
      status: partial
      note: "Parametric DAG engine complete; visual node UI bindings to come"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D13
    feature: "Textiles (weave/knit/drape/cut-room)"
    competitor:
      status: partial
      note: "Cloth simulation for animation/VFX; no garment engineering or cut-room"
      source: "https://docs.blender.org/manual/en/latest/physics/cloth/index.html"
    kerf:
      status: yes
      note: "Weave/knit/drape/cut-room (backend; textiles page)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/textiles"

  - domain: D13
    feature: "Jewelry (configurator)"
    competitor:
      status: no
      note: "General mesh tools only; no jewelry-specific CAD or gem-seat tooling"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "41 modules — ring v4, gemstones v2, settings v3/v4, chain v2"
      evidence: "packages/kerf-jewelry/src/kerf_jewelry"

  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: no
      note: "No BIM or IFC tooling; Architecture Viz add-ons are mesh only"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Revit-comparable engine + IFC4 viewer via /compile-ifc"
      evidence: "packages/kerf-bim/src/kerf_bim"

  # D14 — Cost / materials / LCA
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "No cost engineering or DFM tools"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "6-process Boothroyd-Dewhurst should-cost (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/costing"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: no
      note: "Material system is shader/texture only — no engineering properties"
      source: "https://docs.blender.org/manual/en/latest/render/materials/index.html"
    kerf:
      status: yes
      note: "200 materials (14 families) + Pareto frontier + weighted-score (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/multi_objective.py"

  - domain: D14
    feature: "LCA (full ISO 14040/44 4 phases)"
    competitor:
      status: no
      note: "No lifecycle assessment tooling"
      source: "https://www.blender.org/features/"
    kerf:
      status: yes
      note: "Use+transport+EoL + multi-impact + uncertainty (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/phases.py"
---

# Kerf vs Blender

Blender is a world-class, GPL-licensed DCC tool: mesh-first modelling, sculpting, animation, rigging, Geometry Nodes, and benchmark-quality rendering via Cycles and Eevee. It is not a B-rep parametric CAD application. If you are evaluating Blender for product engineering, jewelry production, or electronics design work, this page lays out where the two tools overlap, where they diverge, and which is the right fit — or whether both belong in your pipeline.

**These are different categories of tool.** Kerf is a B-rep parametric CAD environment with multi-discipline scope (mechanical, electronics, jewelry, architecture). Blender is a mesh-first DCC and animation platform. The overlap is real, but the primary jobs are different.

## Where Blender is strong

- **Free and open-source under GPL.** Blender is fully free — no subscription, no per-seat cost, no cloud account. The GPL licence means the source code is publicly auditable and community-improvable.
- **Mesh-first modelling with BMesh.** Blender's BMesh half-edge data structure gives fast, flexible mesh editing with N-gon support. For concept sculpting and organic forms it is the benchmark tool.
- **Geometry Nodes — a real visual node DAG.** Geometry Nodes is a genuine procedural, mesh-centric node graph: instance scattering, field-driven deformation, simulation nodes. Not CAD parametric history, but a powerful generative toolset with no equivalent in Kerf yet.
- **Sculpting, dyntopo, and multires.** A full sculpt mode with dynamic topology, multi-resolution sculpting, and 30+ brushes. Kerf has no sculpt mode.
- **Cycles and Eevee render quality.** Cycles is a physically-based path tracer with GPU support. Eevee delivers real-time PBR preview. Kerf's heroShot renderer does not match Cycles quality.
- **Animation and rigging.** Full skeletal animation, NLA editor, shape keys, cloth and fluid simulations, and camera animation — capabilities Kerf has no plans to replicate.
- **Vibrant artist community.** Millions of users, Blender Market, BlenderArtists, and an enormous library of tutorials, add-ons, and asset packs.

## What Blender is not (for engineering use)

- **Not a B-rep CAD kernel.** Blender models are polygon meshes, not boundary-representation solids. No analytically exact planes, cylinders, or spline-trimmed surfaces.
- **No NURBS solids.** Blender has NURBS curve objects but no NURBS surfacing in the engineering sense.
- **No STEP B-rep round-trip.** STEP and IGES transfer B-rep geometry that machines and CAM systems expect. Blender exports mesh formats (glTF, FBX, OBJ); there is no B-rep STEP writer.
- **No GD&T or technical drawings.** Engineering drawings with ASME Y14.5 geometric dimensioning and tolerancing are out of scope for Blender by design.
- **Modifier Stack ≠ parametric feature history.** Blender's Modifier Stack is linear per-object and destructive once applied. It does not maintain persistent face IDs.
- **No electronics, no engineering-calc breadth.** There is no schematic editor, no PCB router, no BOM, no simulation pre-compliance.

## Where Kerf is positioned differently

- **B-rep solids with valid topology and tolerances.** Kerf's OCCT kernel produces exact boundary-representation solids whose faces, edges, and vertices carry stable IDs that downstream features, drawings, and CAM paths can reference reliably.
- **Parametric feature history DAG.** The feature tree (pad, pocket, revolve, loft, fillet, draft) is a persistent directed acyclic graph. Editing an early feature regenerates all downstream geometry.
- **Multi-discipline in one workspace.** Electronics (schematic + PCB + DRC + Gerber), jewelry (ring v4, gemstones v2, settings v3/v4, chain v2), 2D drawings, GD&T, CNC CAM, and architecture (IFC) share one environment.
- **STEP / IGES / 3DM B-rep interop.** Manufacturing and supply-chain tooling expects B-rep geometry in neutral exchange formats. Kerf reads and writes STEP and IGES; Blender cannot.
- **MIT open-core, with a hosted option.** The core is permissively MIT-licensed (Blender is copyleft GPL). A hosted SaaS version runs in the browser; a single binary installs locally.
- **Chat-native workflow.** Describe a change in plain language; the LLM edits the feature tree / JSCAD source directly, backed by live doc-search.

## Honest gaps — where Blender wins

- **Render quality: Cycles path-tracer.** Physically-based path tracing with GPU acceleration, volumetrics, caustics, and subsurface scattering. Kerf's heroShot renderer is not in the same class for photoreal output.
- **Sculpting and organic form development.** Dyntopo, multires, retopology, and a full brush library. Kerf has no sculpt mode and is not building one.
- **Animation, rigging, and simulation.** Skeletal animation, NLA, cloth, fluid, particles — a complete film/game pipeline. Kerf has no plans here.
- **Geometry Nodes visual DAG.** A mature, shipped visual node environment for mesh-centric procedural work. Kerf's parametric DAG engine has landed; the visual node UI bindings are still to come.
- **Community and ecosystem depth.** Millions of users, thousands of add-ons, an enormous asset marketplace, and 30 years of accumulated tutorials.

## Side by side

| Feature | Blender | Kerf |
|---|---|---|
| License | ✅ GPL v2+ (free, copyleft) | ✅ MIT open-core (permissive) |
| Cost | ✅ Free, no subscription | ✅ Free local binary; pay-as-you-go hosted |
| Platform | ✅ Win / macOS / Linux desktop | ✅ Browser + single-binary local |
| Hosted / cloud | ❌ Desktop only | ✅ Hosted SaaS + local install |
| B-rep solid kernel | ⚠️ BMesh half-edge — no B-rep | ✅ OCCT B-rep — exact rational |
| Parametric history (feature DAG) | ⚠️ Linear Modifier Stack — not persistent face-ID DAG | ✅ OCCT feature tree + persistent face IDs |
| Constraint sketcher | ❌ None | ✅ Sketcher v2 — geometric + dimensional constraints |
| STEP / IGES B-rep interop | ❌ Mesh export only (glTF/FBX/OBJ) | ✅ STEP / IGES / 3DM B-rep round-trip |
| Visual node DAG | ✅ Geometry Nodes (mesh-centric) | ⚠️ Parametric DAG landed; visual UI to come |
| Sculpting + dyntopo | ✅ Full sculpt mode — dyntopo, multires, 30+ brushes | ⚠️ sculpt_brush (grab/smooth/inflate) + multires; no dyntopo/30+ brushes |
| SubD authoring | ✅ Subdivision Surface modifier + creases | ✅ SubD authoring + creases, poke/extrude, subdivide, SubD→NURBS |
| Path-traced renderer | ✅ Cycles + Eevee (benchmark) | ⚠️ HDRI + ACES + bloom (heroShot.js); no full path tracer |
| Animation / rigging | ✅ Full skeletal, NLA, cloth sim | ❌ No animation or rigging |
| GD&T / tolerances | ❌ None | ✅ ASME Y14.5 datum + tolerance framework |
| 2D technical drawings | ❌ None | ✅ Multi-sheet drawings |
| Electronics / PCB | ❌ Not applicable | ✅ Full EDA — schematic, routing, DRC, Gerber/IPC-2581 |
| CNC CAM | ❌ None | ✅ 3-axis CAM + tool DB; 5-axis 3+2 |
| Chat / LLM editing | ❌ None | ✅ Chat-native — edits feature tree per turn |
| Python scripting | ✅ bpy — full in-process Python API | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
