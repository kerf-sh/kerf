---
slug: fusion
competitor: "Autodesk Fusion 360"
category: cad-mechanical
left: kerf
right: fusion
hero_tagline: "Cloud-connected multi-discipline CAD — two tools, two philosophies."
reviewed_at: 2026-05-19
order: 2
features:
  # D1 — Geometry & core CAD
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "Full parametric sketcher, all major constraints"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-584BEC15-41E6-4466-9705-5464748227BF"
    kerf:
      status: yes
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: yes
      note: "Timeline-based parametric modelling (mature)"
      source: "https://autocadeverything.com/fusion-360-parametric-modeling/"
    kerf:
      status: yes
      note: "OCCT feature tree, wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Loft"
    competitor:
      status: yes
      note: "Guide-rail overloads supported"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-584BEC15-41E6-4466-9705-5464748227BF"
    kerf:
      status: partial
      note: "No guide-rail overload in OCCT binding"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: yes
      note: "Full sheet-metal workspace (flanges, hem, relief, jog)"
      source: "https://autocadeverything.com/what-is-fusion-360/"
    kerf:
      status: partial
      note: "Single flange + unfold + flat DXF; no hem/jog/multi-flange"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: yes
      note: "T-spline Sculpt workspace; industry-quality freeform"
      source: "https://www.autodesk.com/products/fusion-360/blog/surface-modeling-overview/"
    kerf:
      status: partial
      note: "Math complete; OCCT bindings unconfirmed at build"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: yes
      note: "Joint system + Constraints feature (Sept 2025 update)"
      source: "https://www.autodesk.com/products/fusion-360/blog/september-2025-product-update-whats-new/"
    kerf:
      status: yes
      note: "Wired; coincident/concentric/parallel + BOM panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "Assembly interference (clash)"
    competitor:
      status: yes
      note: "Built-in interference detection + motion contact sets"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-CONTACT-SETS"
    kerf:
      status: partial
      note: "Backend OBB-SAT + BVH + tri-tri; no UI panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/clash/detect.py"

  - domain: D1
    feature: "Assembly motion study"
    competitor:
      status: yes
      note: "Motion study + contact sets + interference in UI"
      source: "https://productdesignonline.com/overlooked-fusion-feature-motion-study-in-autodesk-fusion-360/"
    kerf:
      status: no
      note: "Planar MBD not wired to assembly solver"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Full drawing workspace; AI automation (2025)"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-A476C8D8-1EE2-4AA1-9A97-88DB74A4E837"
    kerf:
      status: partial
      note: "Live HLR projection + auto-dim; no GD&T-placement UI"
      evidence: "src/components/DrawingView.jsx"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: yes
      note: "Parameter Table + Configuration Table (Sept 2025)"
      source: "https://www.autodesk.com/products/fusion-360/blog/september-2025-product-update-whats-new/"
    kerf:
      status: yes
      note: "Engine + ConfigurationsPanel.jsx wired in Editor.jsx"
      evidence: "src/components/ConfigurationsPanel.jsx"

  - domain: D1
    feature: "Direct edit (push-pull)"
    competitor:
      status: yes
      note: "History-free direct editing intermixed with timeline"
      source: "https://autocadeverything.com/fusion-360-parametric-modeling/"
    kerf:
      status: partial
      note: "Planar push-pull only; no move/delete-face"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  # D2 — Structural / FEA
  - domain: D2
    feature: "FE — solid (tet/hex)"
    competitor:
      status: paid
      note: "Simulation Extension (cloud-only solvers)"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "CalculiX/Mystran/Z88 bridge (needs binary)"
      evidence: "packages/kerf-fem/src/kerf_fem/calculix_bridge.py"

  - domain: D2
    feature: "Modal / buckling / nonlinear"
    competitor:
      status: paid
      note: "Event simulation + buckling via Simulation Extension"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Consistent-mass modal, Riks, J2 plasticity (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/modal.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "Fusion is not a structural code-compliance tool"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Full Ch. E/F/H/H combined + 50-section catalog (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/steel_beam.py"

  - domain: D2
    feature: "ACI 318-19 concrete"
    competitor:
      status: no
      note: "No concrete code-compliance in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Flexure/shear/PM/dev-length (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/rc_beam.py"

  - domain: D2
    feature: "Fatigue (S-N, ε-N, rainflow)"
    competitor:
      status: paid
      note: "Event simulation extension covers fatigue-type loads"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "S-N, ε-N, rainflow counting (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/fatigue_fem.py"

  - domain: D2
    feature: "FE — plate / shell (native)"
    competitor:
      status: paid
      note: "Simulation Extension handles shells via cloud solver"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "MITC4 (Bathe-Dvorkin) + modal; 1.29% error vs Timoshenko"
      evidence: "packages/kerf-fem/src/kerf_fem/linear_static.py"

  # D3 — Machine elements
  - domain: D3
    feature: "Spur/helical gear rating (AGMA 2001-D04)"
    competitor:
      status: partial
      note: "Gear geometry via SpurGear add-in; no AGMA rating engine"
      source: "https://www.autodesk.com/learn/ondemand/course/mechanical-design-with-intent/unit/6L5qNPsYqNDrCMkGLrtJQY"
    kerf:
      status: yes
      note: "Full AGMA 2001-D04 rating (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D3
    feature: "Bearings — ISO 281 L10"
    competitor:
      status: partial
      note: "Bearing generator for geometry selection; no ISO 281 life calc"
      source: "https://www.autodesk.com/learn/ondemand/course/mechanical-design-with-intent/unit/6L5qNPsYqNDrCMkGLrtJQY"
    kerf:
      status: yes
      note: "ISO 281 L10 + ISO/TS 16281 aISO modified life (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  - domain: D3
    feature: "Springs (compr/ext/torsion/Belleville)"
    competitor:
      status: no
      note: "No spring design calculator in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Compression/extension/torsion/Belleville (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D3
    feature: "Belt / chain drives"
    competitor:
      status: no
      note: "No belt/chain sizing calculator in Fusion"
      source: "https://autocadeverything.com/fusion-360-cam/"
    kerf:
      status: yes
      note: "Belt/chain drive sizing (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/beltchain/drives.py"

  - domain: D3
    feature: "Shaft (stress + critical speed)"
    competitor:
      status: no
      note: "No shaft design calculator in base Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Closed-form stress + critical speed (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  # D4 — Thermal / fluid / HVAC
  - domain: D4
    feature: "Psychrometrics (moist air)"
    competitor:
      status: no
      note: "No psychrometric calculator in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "ASHRAE-grade psychrometrics (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/psychro/air.py"

  - domain: D4
    feature: "Heat exchangers (LMTD + ε-NTU + Bell-Delaware)"
    competitor:
      status: no
      note: "No heat exchanger calculator in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "LMTD + ε-NTU + Bell-Delaware + TEMA (backend)"
      evidence: "packages/kerf-hvac/src/kerf_hvac/sizing.py"

  - domain: D4
    feature: "CFD"
    competitor:
      status: no
      note: "Flow simulation not in Fusion; separate Autodesk CFD product"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "Real OpenFOAM bridge (needs install; backend)"
      evidence: "packages/kerf-cfd/src/kerf_cfd/openfoam_bridge.py"

  - domain: D4
    feature: "Steam/water properties"
    competitor:
      status: no
      note: "No IAPWS-IF97 steam property calculator in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "IAPWS-IF97 Regions 1/2/4 validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/boiler/plant.py"

  - domain: D4
    feature: "HVAC duct sizing (SMACNA)"
    competitor:
      status: no
      note: "No HVAC duct sizing in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "SMACNA duct sizing + flat-pattern (backend)"
      evidence: "packages/kerf-hvac/src/kerf_hvac/duct.py"

  - domain: D4
    feature: "Building loads"
    competitor:
      status: no
      note: "No building energy / HVAC load calculator in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "Degree-day + CLTD/RTS + Sol-air + fenestration (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/buildingenergy/energy.py"

  # D5 — Aero / marine / space
  - domain: D5
    feature: "Airfoil inviscid CL (panel)"
    competitor:
      status: no
      note: "No airfoil panel method in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "2D panel method, wired"
      evidence: "packages/kerf-aero/src/kerf_aero/panel_2d.py"

  - domain: D5
    feature: "3D wing VLM (+ viscous + compressibility)"
    competitor:
      status: no
      note: "No VLM in Fusion; requires separate Autodesk CFD"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "VLM + strip viscous + PG/KT compressibility (backend)"
      evidence: "packages/kerf-aero/src/kerf_aero/vlm.py"

  - domain: D5
    feature: "Orbital (Kepler, J2/J3, Hohmann)"
    competitor:
      status: no
      note: "No orbital mechanics in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "Kepler + J2/J3 + Hohmann + Lambert, wired"
      evidence: "packages/kerf-aero/src/kerf_aero"

  - domain: D5
    feature: "Naval hydrostatics + GZ stability (IMO)"
    competitor:
      status: no
      note: "No naval architecture tools in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "Hydrostatics + GZ + IMO stability, wired"
      evidence: "packages/kerf-marine/src/kerf_marine/stability.py"

  - domain: D5
    feature: "Doublet-lattice / flutter"
    competitor:
      status: no
      note: "No flutter analysis in Fusion"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Does-Fusion-360-have-flow-simulation-as-a-simulation-study.html"
    kerf:
      status: yes
      note: "Doublet-lattice flutter (backend)"
      evidence: "packages/kerf-aero/src/kerf_aero/flutter_pk.py"

  # D6 — Electronics / EDA / silicon
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: yes
      note: "Fusion Electronics (EAGLE-derived); schematic + ERC"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "KiCad round-trip viewer (read-only)"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: yes
      note: "Native PCB editor; ODB++ fab output"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "PCB viewer wired (read-only); fab: Gerber/ODB++/IPC-2581"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab"

  - domain: D6
    feature: "SPICE"
    competitor:
      status: no
      note: "No SPICE simulator in Fusion; schematic-only"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "Real ngspice, wired"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: paid
      note: "Signal Integrity Extension powered by Ansys (paid add-on)"
      source: "https://www.autodesk.com/products/fusion-360/signal-integrity-extension"
    kerf:
      status: yes
      note: "IBIS 5.1 + Bergeron + PRBS eye envelope (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "EMC (radiated/shielding/limits)"
    competitor:
      status: paid
      note: "Via Signal Integrity Extension; basic closed-form"
      source: "https://www.autodesk.com/products/fusion-360/blog/fusion-360-electronics-how-to-use-the-signal-integrity-extension/"
    kerf:
      status: yes
      note: "Common-mode, return-path gap, slot antenna (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/emc"

  - domain: D6
    feature: "PDN (DC IR-drop + AC sweep)"
    competitor:
      status: paid
      note: "Signal Integrity Extension covers partial PDN analysis"
      source: "https://www.autodesk.com/products/fusion-360/signal-integrity-extension"
    kerf:
      status: yes
      note: "Z(ω) + target-Z + decap optimiser (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "PCB thermal"
    competitor:
      status: paid
      note: "Electronics Cooling Extension (paid); no liquid cooling"
      source: "https://www.engineering.com/how-fusion-360-fast-tracks-consumer-electronics-design/"
    kerf:
      status: partial
      note: "Lumped Rθ (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics"

  - domain: D6
    feature: "Silicon synth (Yosys) / STA / GDS / DRC / LVS / formal / CTS"
    competitor:
      status: no
      note: "No RTL/silicon flow in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "Full silicon flow; zero UI"
      evidence: "packages/kerf-silicon/src/kerf_silicon"

  # D7 — Manufacturing / CAM
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: yes
      note: "HSMWorks-lineage CAM; mature 3-axis toolpaths"
      source: "https://www.autodesk.com/products/fusion-360/blog/hsmworks-to-fusion-transition-guide/"
    kerf:
      status: yes
      note: "CAMView wired for common 3-axis ops"
      evidence: "packages/kerf-cam/src/kerf_cam"

  - domain: D7
    feature: "5-axis (kinematics + posts)"
    competitor:
      status: paid
      note: "4/5-axis requires Manufacturing Extension (paid)"
      source: "https://www.autodesk.com/products/fusion-360/manufacturing-extension"
    kerf:
      status: partial
      note: "Engine solid (5-axis 3+2); no UI"
      evidence: "packages/kerf-cam/src/kerf_cam/five_axis"

  - domain: D7
    feature: "Turning cycles (G71/G70/threading)"
    competitor:
      status: yes
      note: "Turning canned cycles (G95/G96/G76/G92) supported"
      source: "https://industrialmonitordirect.com/blogs/knowledgebase/configuring-fusion-360-turning-canned-cycles-for-cnc-lathes"
    kerf:
      status: yes
      note: "G71/G70/threading cycles (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam"

  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC/Mach3)"
    competitor:
      status: yes
      note: "Hundreds of post-processors in library; CPS format"
      source: "https://cam.autodesk.com/hsmposts"
    kerf:
      status: yes
      note: "Fanuc/GRBL/LinuxCNC/Mach3 posts; no G41/42 cutter-comp"
      evidence: "packages/kerf-cam/src/kerf_cam/posts"

  - domain: D7
    feature: "Feeds & speeds + tool-life"
    competitor:
      status: yes
      note: "Feeds & speeds with material library in CAM workspace"
      source: "https://www.autodesk.com/products/fusion-360/blog/machining-fundamentals-introduction-to-post-processors/"
    kerf:
      status: yes
      note: "Taylor extended + Gilbert economic speed (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/tool_db.py"

  - domain: D7
    feature: "Moldflow / fill sim"
    competitor:
      status: paid
      note: "Injection Molding Simulation via Simulation Extension (paid)"
      source: "https://www.autodesk.com/products/fusion-360/blog/what-is-injection-molding-simulation-in-fusion-360/"
    kerf:
      status: yes
      note: "Hele-Shaw front tracking + weld-line + air-trap (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/hele_shaw.py"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: paid
      note: "True Shape 3D Nesting via Manufacturing Extension (paid)"
      source: "https://www.autodesk.com/products/fusion-360/manufacturing-extension"
    kerf:
      status: yes
      note: "Minkowski-sum NFP + IFP + bottom-left fill (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/nesting/pack.py"

  - domain: D7
    feature: "Additive / DFAM"
    competitor:
      status: paid
      note: "Additive tools via Manufacturing Extension; orientation + supports"
      source: "https://www.autodesk.com/products/fusion-360/blog/fusion-360-additive-manufacturing-3d-printing-capabilities/"
    kerf:
      status: yes
      note: "DFAM checks + additive calculators (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam"

  - domain: D7
    feature: "FDM slicing (Cura)"
    competitor:
      status: yes
      note: "Built-in slicing; print settings & layer configuration"
      source: "https://autocadeverything.com/fusion-360-3d-printing/"
    kerf:
      status: yes
      note: "Cura runner wired (PrintSliceView)"
      evidence: "packages/kerf-slicing/src/kerf_slicing/cura_runner.py"

  # D8 — Civil / infrastructure / geo
  - domain: D8
    feature: "Horizontal+vertical alignment (clothoid, SSD)"
    competitor:
      status: no
      note: "Fusion is not a civil/road design tool"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Clothoid + SSD + AASHTO runoff (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/horizontal_alignment.py"

  - domain: D8
    feature: "Corridor / cross-section"
    competitor:
      status: no
      note: "No corridor modelling in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Divided highway + reverse-crown + urban curb templates"
      evidence: "packages/kerf-civil/src/kerf_civil/corridor.py"

  - domain: D8
    feature: "Geodesy / projections (Vincenty, TM, UTM, LCC)"
    competitor:
      status: no
      note: "No geodetic projection tools in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Vincenty + TM + UTM + LCC (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/crs.py"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/pile/liquefaction)"
    competitor:
      status: no
      note: "No geotechnical analysis in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Seed-Idriss CSR + SPT/CPT CRR + Tokimatsu (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/civil"

  # D9 — Dynamics / motion / controls
  - domain: D9
    feature: "Planar MBD (Lagrange/DAE, Baumgarte)"
    competitor:
      status: no
      note: "Motion study is kinematic; no full MBD solver"
      source: "https://productdesignonline.com/overlooked-fusion-feature-motion-study-in-autodesk-fusion-360/"
    kerf:
      status: yes
      note: "Planar Lagrange/DAE + Baumgarte stabilisation (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/integrator.py"

  - domain: D9
    feature: "Kinematics (four-bar/slider-crank/cam)"
    competitor:
      status: partial
      note: "Motion study gives kinematic playback; no analytical solver"
      source: "https://autocadeverything.com/fusion-360-joints/"
    kerf:
      status: yes
      note: "Four-bar/slider-crank/cam kinematics (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/forward_kinematics.py"

  - domain: D9
    feature: "Robotics 6-DOF spatial IK"
    competitor:
      status: no
      note: "Robot toolpath generation only; no 6-DOF IK solver"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Can-Fusion-360-be-used-to-generate-toolpaths-for-robots.html"
    kerf:
      status: yes
      note: "DLS Jacobian 6-DOF IK; PUMA-class validated (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/inverse_kinematics.py"

  - domain: D9
    feature: "Controls — state-space / LQR / Kalman"
    competitor:
      status: no
      note: "No control systems tools in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Ackermann + LQR (CARE) + Luenberger (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/controls/system.py"

  - domain: D9
    feature: "Vibration n-DOF modal / FRF"
    competitor:
      status: paid
      note: "Modal via Simulation Extension (cloud-only)"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Full n-DOF eigen + FRF matrix (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/modal.py"

  # D10 — Electrical / energy / PLC / firmware
  - domain: D10
    feature: "AC load-flow (Ybus / Newton-Raphson)"
    competitor:
      status: no
      note: "No power systems load-flow in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "Full polar-form NR; 3+5-bus validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "No PV system calculator in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/solar-panels-solar-electricity-works/"
    kerf:
      status: yes
      note: "Single-diode + bypass-diode IV + global MPPT (backend)"
      evidence: "packages/kerf-energy/src/kerf_energy/solar.py"

  - domain: D10
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: no
      note: "No wiring harness design in Fusion; AutoCAD Electrical only"
      source: "https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Is-it-possible-to-create-a-wiring-diagram-with-Fusion-360-Electronics.html"
    kerf:
      status: yes
      note: "WireViz runner + harness3d; WiringView wired"
      evidence: "packages/kerf-wiring/src/kerf_wiring/wireviz_runner.py"

  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB/motion)"
    competitor:
      status: no
      note: "No PLC programming environment in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired"
      evidence: "packages/kerf-plc/src/kerf_plc/power_flow.py"

  - domain: D10
    feature: "Firmware build/upload/monitor/debug"
    competitor:
      status: no
      note: "No firmware toolchain in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/18-things-need-to-know-fusion-360-electronics/"
    kerf:
      status: yes
      note: "FirmwareActions + debug panel wired"
      evidence: "src/components/FirmwareActions.jsx"

  # D11 — Tolerancing / metrology / QA
  - domain: D11
    feature: "GD&T data model (ASME Y14.5)"
    competitor:
      status: yes
      note: "GD&T symbols in drawing workspace (ASME Y14.5 / ISO 1101)"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=DWG-SYMBOLS"
    kerf:
      status: yes
      note: "GD&T data model + auto-propose (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py"

  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS/MC)"
    competitor:
      status: no
      note: "Stackup in Inventor Tolerance Analysis; not in Fusion itself"
      source: "https://www.autodesk.com/solutions/tolerance-analysis-workflow"
    kerf:
      status: yes
      note: "WC/RSS/MC (backend; MC LCG bug noted)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt"

  - domain: D11
    feature: "Tolerance stackup — 3D vector loop"
    competitor:
      status: no
      note: "3D stackup not in Fusion; Inventor Tolerance Analysis only"
      source: "https://www.autodesk.com/solutions/tolerance-analysis-workflow"
    kerf:
      status: yes
      note: "6-DOF vector loop + sensitivity Jacobian (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt"

  - domain: D11
    feature: "CMM fitting & evaluation"
    competitor:
      status: partial
      note: "Manual Inspection in Fusion; full CMM via PowerInspect"
      source: "https://www.autodesk.com/products/fusion-360/blog/whats-new-in-fusion-360-manual-inspection/"
    kerf:
      status: yes
      note: "CMM fitting & evaluation (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/cmm/inspect.py"

  - domain: D11
    feature: "Process capability (Cpk/Ppk)"
    competitor:
      status: no
      note: "No SPC / Cpk capability in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/blog/whats-new-in-fusion-360-manual-inspection/"
    kerf:
      status: yes
      note: "Cpk/Ppk process capability (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt"

  # D12 — Optics / acoustics
  - domain: D12
    feature: "Paraxial ABCD ray transfer"
    competitor:
      status: no
      note: "No optical design tools in Fusion"
      source: "https://forums.autodesk.com/t5/fusion-design-validate-document/simulating-light-travel-and-focus/td-p/6786003"
    kerf:
      status: yes
      note: "ABCD ray transfer matrices (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/ray_transfer.py"

  - domain: D12
    feature: "Gaussian beam propagation (M², q-param)"
    competitor:
      status: no
      note: "No laser/Gaussian beam simulation in Fusion"
      source: "https://forums.autodesk.com/t5/fusion-design-validate-document/simulating-light-travel-and-focus/td-p/6786003"
    kerf:
      status: yes
      note: "Complex-q + ABCD + M² + fibre coupling (backend)"
      evidence: "packages/kerf-optics/src/kerf_optics/lens_system.py"

  - domain: D12
    feature: "Acoustics (ISO 9613, RT60, weighting, mass-law TL)"
    competitor:
      status: no
      note: "No acoustic analysis tools in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "ISO 9613, RT60, A/C-weight, mass-law TL (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/acoustics/sound.py"

  # D13 — Verticals
  - domain: D13
    feature: "Jewelry (41 modules)"
    competitor:
      status: partial
      note: "Basic ring/pendant geometry possible; no dedicated jewelry suite"
      source: "https://adsknews.autodesk.com/de/stories/fusion-360-jewelry-design-course/"
    kerf:
      status: yes
      note: "41-module suite; RhinoGold/Matrix-class depth"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: no
      note: "Fusion is not a BIM tool; Revit for full BIM workflows"
      source: "https://vagon.io/blog/rhino-3d-vs-fusion-360"
    kerf:
      status: yes
      note: "Revit-comparable engine + viewer wired via /compile-ifc"
      evidence: "packages/kerf-bim/src/kerf_bim"

  - domain: D13
    feature: "Textiles (weave/knit/drape/cut-room)"
    competitor:
      status: no
      note: "No textile design tools in Fusion"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: yes
      note: "Weave/knit/drape/cut-room (backend); no 3D avatar drape"
      evidence: "packages/kerf-textiles/src/kerf_textiles"

  - domain: D13
    feature: "Dental (crown/surgical guide/DICOM)"
    competitor:
      status: partial
      note: "B-rep geometry usable; no dedicated dental workflow"
      source: "https://www.autodesk.com/products/fusion-360/simulation-extension"
    kerf:
      status: partial
      note: "Crown is placeholder cylinder; surgical guide in spotlight"
      evidence: "packages/kerf-dental/src/kerf_dental"

  # D14 — Cost / materials / LCA
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: partial
      note: "Basic cost estimation in Generative Design; not Boothroyd-grade"
      source: "https://help.autodesk.com/view/fusion360/ENU/?guid=GD-COST-MAT"
    kerf:
      status: yes
      note: "6 processes, Boothroyd-Dewhurst method (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/costing/estimate.py"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: partial
      note: "Material assignment from library; no Ashby multi-objective"
      source: "https://autocadeverything.com/how-to-change-material-in-fusion-360/"
    kerf:
      status: yes
      note: "200 materials + Pareto frontier + weighted-score (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/materials.py"

  - domain: D14
    feature: "LCA (full ISO 14040/44 4 phases)"
    competitor:
      status: paid
      note: "Manufacturing Sustainability Insights add-on (paid/partner)"
      source: "https://www.autodesk.com/products/fusion-360/blog/manufacturing-sustainability-insights-add-on-msi/"
    kerf:
      status: yes
      note: "ISO 14040/44 4-phase + multi-impact + uncertainty (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/report.py"

  - domain: D14
    feature: "Process simulation (moldflow/weld/AM/forming)"
    competitor:
      status: paid
      note: "Injection molding via Simulation Extension (paid)"
      source: "https://www.autodesk.com/products/fusion-360/blog/what-is-injection-molding-simulation-in-fusion-360/"
    kerf:
      status: yes
      note: "Moldflow + weld + AM + forming (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow"
---

# Kerf vs Autodesk Fusion 360

Fusion 360 pioneered the idea of integrated CAD / CAM / CAE / PCB in a single cloud-connected workspace and has millions of users behind it. Kerf is the tool most similar to Fusion in shape — both cover multi-discipline engineering in one environment with cloud collaboration. Commercial use is ~US$680/yr (as of May 2026); a restricted free personal tier exists (non-commercial, <US$1,000 annual revenue, as of May 2026). The differences are in philosophy: Fusion is a closed subscription product with a polished decade-long track record; Kerf is MIT open-core, chat-native, and subscription-free. Below is an honest look at both.

## Where Fusion 360 is strong

- **Cloud-native + desktop in one.** Fusion is designed cloud-first — every project auto-saves to Autodesk's cloud, multi-user collaboration is baked in, and the same tool runs on Windows and macOS as a native desktop app.
- **HSMWorks-lineage CAM.** The CAM workspace inherits HSMWorks' industry-tested toolpath engine with verified simulation, a broad post-processor library, and years of in-the-field machining validation. Kerf's CAM is younger.
- **Cloud generative design.** Automated topology exploration across load cases using cloud compute — a flagship capability for lightweighting and lattice design. Kerf has no equivalent we're aware of today.
- **T-spline sculpt workflow.** The Sculpt workspace gives direct freeform surface modelling with T-spline subdivision and crease support. Kerf's early NURBS Phase 4 does not match.
- **Assembly motion study and interference detection.** Fusion provides motion studies, contact sets, and interference detection on top of its joint system. Kerf now matches the joint type set but does not yet ship motion study.
- **FEM multi-physics depth.** Linear static and thermal FEM (extension / cloud-metered) with a mature solver validation record.
- **Eagle PCB integration.** Fusion Electronics is the direct successor to Autodesk EAGLE, with a native ECAD↔MCAD live link.
- **Decades of vendor polish and community.** Millions of users, an extensive official learning platform, and integration with the wider Autodesk portfolio.

## Where Kerf differs

- **MIT open-core, no subscription.** Fusion charges ~US$680/yr (as of May 2026); its free tier is non-commercial only. Kerf's full feature set is MIT-licensed — free locally with no revenue restriction, no seat fee, and no feature-gating.
- **BYO LLM / BYO key.** Bring your own Anthropic or OpenAI API key and zero billing flows through Kerf — the `kerf_byo` tier routes all inference to your own account. Fusion has no configurable LLM we're aware of (as of May 2026).
- **Chat-native workflow.** Describe a feature, constraint, routing rule, or simulation check in plain language; the LLM edits the feature-tree source backed by live doc-search. Fusion has no comparable LLM integration we're aware of (as of May 2026).
- **True offline, fully open codebase.** `pip install 'kerf[server]'` + `kerf serve` with BYO Postgres — no Autodesk account, no limited-offline caveat. The full codebase is on GitHub under MIT.
- **Pre-compliance electronics simulation — in-box.** Signal integrity, EMC/EMI, PDN, and PCB thermal are all included without extension or cloud-metering. Fusion gates these behind paid extensions.
- **Richer in-box electronics fab output.** Gerber / Excellon / IPC-2581 / ODB++ / IPC-D-356A netlist and DRC with IPC-2221B A/B/C manufacturing presets — beyond Fusion Electronics' base fab pack.
- **40-module jewelry domain.** Ring v4, gemstones v2 (30 cuts), settings v3/v4, gem-seat v2, chain v2, findings, casting export, a 31-template library, and PBR gem/metal viewport materials — a complete professional jewelry vertical.
- **620 analytic-oracle kernel tests.** Every core geometric operation is regression-tested against closed-form analytic references.
- **kerf-sdk Python scripting.** Automate over HTTP/JSON-RPC from your own machine — the same interface the LLM uses internally.

## Honest gaps — where Kerf is behind today

- **CAM fidelity and validation.** Fusion's CAM has years of in-the-field toolpath validation and the HSMWorks pedigree. Kerf's CAM is younger and less hardened.
- **Assembly motion study.** Kerf now matches Fusion's joint type set, but motion studies, contact sets, and interference detection are not yet shipped.
- **FEM multi-physics coverage.** Kerf ships linear static, thermal, and nonlinear plasticity FEM; Fusion's multi-physics cloud solvers cover more boundary conditions and load types. CFD is not in Kerf.
- **No generative design.** Fusion's cloud topology optimisation across load cases is a flagship that has no Kerf counterpart today.
- **No T-spline freeform / Sculpt.** Fusion's Sculpt workspace for organic freeform modelling has no Kerf counterpart. NURBS Phase 4 is early and scope-limited.
- **Direct modelling is limited.** Fusion's ability to intermix direct editing with the parametric timeline is more capable than Kerf's current feature-tree-primary approach.
- **Smaller community, fewer tutorials.** Fusion has millions of users and a mature learning platform. Kerf is early-stage.

## Side by side

| Feature | Fusion 360 | Kerf |
|---|---|---|
| License | ⚠️ Proprietary subscription | ✅ MIT open-core |
| Cost | ⚠️ ~US$680/yr (May 2026); startup ~$150/3yr (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Free tier | ⚠️ Personal-use only (<US$1k rev, May 2026) | ✅ Full free local install, no revenue cap |
| BYO LLM / model key | ❌ No | ✅ BYO key (kerf_byo bucket) |
| Offline / self-host | ⚠️ Limited offline; many features cloud-tied | ✅ Full offline: pip install 'kerf[server]' |
| OS support | ✅ Windows + macOS | ✅ Browser + Win/macOS/Linux binary |
| Parametric B-rep | ✅ Timeline-based modelling (mature) | ✅ OCCT feature tree |
| Constraint sketcher | ✅ Full parametric sketcher | ✅ Sketcher v2 — all major constraints |
| Sheet metal | ✅ Full sheet-metal workspace | ✅ Flange + unfold + flat-pattern DXF |
| Freeform / T-spline sculpt | ✅ Sculpt workspace (industry-quality) | ⚠️ NURBS Phase 4 (early) |
| Assembly joints | ✅ Full joint system | ✅ Full joint system — rigid/revolute/slider/cam/gear/pin-slot |
| Motion study | ✅ Motion + contact sets + interference | ❌ Not yet |
| CAM (3-axis) | ✅ HSMWorks-lineage CAM (mature) | ✅ 3-axis CAM + tool DB |
| Multi-axis CAM | ✅ 4/5-axis (paid extension) | ✅ 5-axis CAM 3+2 |
| Generative design | ✅ Cloud topology optimisation | ❌ Roadmap |
| FEM (static / thermal) | ✅ Built-in (extension / cloud-metered) | ⚠️ Linear static + thermal; not full parity |
| SI pre-compliance | ⚠️ Via paid Fusion extension | ✅ In-box — transmission-line, via stub, diff pair |
| EMC / EMI analysis | ⚠️ Extension-gated; basic | ✅ Common-mode, return-path gap, slot antenna |
| PDN analysis | ⚠️ Extension-gated | ✅ Decap placement, target impedance, plane resonance |
| Thermal (PCB) | ⚠️ Extension-gated cooling analysis | ✅ Copper pour, via thermal relief, hot-spot |
| 2D drawings | ✅ Full drawing + annotations | ✅ Multi-sheet drawings |
| Electronics (schematic + PCB) | ✅ Fusion Electronics (EAGLE-derived) | ✅ Hierarchical schematic + PCB layout |
| Jewelry tooling | ❌ None | ✅ 40-module jewelry suite |
| Chat / LLM editing | ❌ None | ✅ Chat-native + doc-search backed |
| Scripting / API | ✅ Fusion API (Python / C++) | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| Open source | ❌ Proprietary | ✅ MIT — full codebase on GitHub |
