---
slug: creo
competitor: PTC Creo
category: cad-mechanical
left: kerf
right: creo
hero_tagline: "Creo invented the parametric feature tree — Kerf brings that same discipline to teams who can't afford the subscription."
reviewed_at: 2026-05-24
features:
  # ── D1 Geometry & core CAD ───────────────────────────────────────────────
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "Creo Sketcher — fully parametric, mature constraint solving; intent manager auto-applies constraints"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/sketcher/sketcher_intro.html"
    kerf:
      status: yes
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/sketch.py"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: yes
      note: "Extrude / Cut Extrude / Revolve — foundational Creo features; fully bidirectional parametric"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "OCCT feature tree, wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Fillet / chamfer (constant)"
    competitor:
      status: yes
      note: "Round / Chamfer with constant, variable, and full-round options"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/rounds/rounds_intro.html"
    kerf:
      status: yes
      note: "Constant fillet + chamfer wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Variable-radius fillet"
    competitor:
      status: yes
      note: "Variable-radius round with multiple driving points along edge"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/rounds/rounds_intro.html"
    kerf:
      status: yes
      note: "Runtime-probed law binding for variable-radius fillet"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Shell / hollow"
    competitor:
      status: yes
      note: "Shell feature with exclusion of selected faces, multiple thickness"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "Shell/hollow wired via OCCT"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Sweep (1 & 2 rail)"
    competitor:
      status: yes
      note: "Swept Blend / Sweep along trajectory; multi-section sweeps with tangency control"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "BRepOffsetAPI_MakePipeShell; 1 & 2 rail"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Loft"
    competitor:
      status: yes
      note: "Boundary Blend — full guide-curve and tangency overloads"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: partial
      note: "No guide-rail overload in OCCT binding"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/feature_loft.py"

  - domain: D1
    feature: "Patterns (linear/polar) + mirror"
    competitor:
      status: yes
      note: "Pattern (linear/directional/radial/curve/fill) + Mirror; relation-driven"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "Linear/polar pattern + mirror wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/routes.py"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: yes
      note: "Creo Sheet Metal workbench — flange, hem, relief, jog, unbend, flat pattern, DXF/DWG"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/sheetmetal/sheetmetal_intro.html"
    kerf:
      status: partial
      note: "Single flange + unfold + flat DXF; no hem/relief/jog/multi-flange"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/sheet_metal.py"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: yes
      note: "Creo Style (ISDX) — Class-A NURBS surfacing, curve networks, curvature continuity"
      source: "https://www.ptc.com/en/products/creo/options/style"
    kerf:
      status: partial
      note: "Math complete; OCCT bindings unconfirmed at build"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: yes
      note: "Assembly constraints (Coincident, Offset, Parallel, Angle, Tangent, etc.); fully bidirectional"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/assembly/assembly_intro.html"
    kerf:
      status: yes
      note: "Wired: coincident/concentric/parallel/angle + BOM panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "Large assembly / simplified representations"
    competitor:
      status: yes
      note: "Simplified Representations + Shrinkwrap + Lightweight Graphics for 1000+ component assemblies"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/assembly/simplified_reps/simplified_reps_intro.html"
    kerf:
      status: partial
      note: "LOD mesh swapping configurable; no formal simplified-rep workflow"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Creo Drawing — live B-rep projection, auto BOM, GD&T callouts, tolerance notes"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/drawing/drawing_intro.html"
    kerf:
      status: partial
      note: "Template-based; not live B-rep projection; no UI panel"
      evidence: "src/components/DrawingView.jsx"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: yes
      note: "Family Tables — parametric instance tables for part/assembly families"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/family_tables/family_tables_intro.html"
    kerf:
      status: yes
      note: "Engine complete; no UI panel"
      evidence: "src/components/ConfigurationsPanel.jsx"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: yes
      note: "Boolean merge/cut on arbitrary NURBS solids via Granite One kernel; battle-hardened heal"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "OCCT booleans; no graceful fuzzy-heal on near-miss geometry"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/occ_helpers.py"

  # ── D2 Structural / FEA ───────────────────────────────────────────────────
  - domain: D2
    feature: "FE — solid (tet/hex)"
    competitor:
      status: paid
      note: "Creo Simulate (Mechanica) — p-element adaptive FEM for structural/thermal; separate paid module"
      source: "https://www.ptc.com/en/products/creo/options/simulate"
    kerf:
      status: yes
      note: "CalculiX/Mystran/Z88 bridge (needs binary; backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/calculix_bridge.py"

  - domain: D2
    feature: "Modal / buckling / nonlinear"
    competitor:
      status: paid
      note: "Creo Simulate — Modal, Prestress Modal, Buckling, dynamic frequency response"
      source: "https://www.ptc.com/en/products/creo/options/simulate"
    kerf:
      status: yes
      note: "Consistent-mass modal, Riks, J2 plasticity (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/modal.py"

  - domain: D2
    feature: "FE — plate / shell (native)"
    competitor:
      status: paid
      note: "Creo Simulate — shell idealisation from midsurface extraction"
      source: "https://www.ptc.com/en/products/creo/options/simulate"
    kerf:
      status: yes
      note: "MITC4 (Bathe-Dvorkin) + modal; 1.29% error vs Timoshenko (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/linear_static.py"

  - domain: D2
    feature: "Fatigue (S-N, ε-N, rainflow)"
    competitor:
      status: paid
      note: "Creo Simulate — Fatigue Advisor module; S-N and rainflow counting"
      source: "https://www.ptc.com/en/products/creo/options/simulate"
    kerf:
      status: yes
      note: "S-N, ε-N, rainflow counting (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem/fatigue_fem.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "Creo is a geometry/simulation tool; no structural code-compliance checks"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Full Ch. E/F/H + 50-section catalog (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  - domain: D2
    feature: "ASCE 7-22 seismic"
    competitor:
      status: no
      note: "No seismic load analysis in Creo"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "ELF + RSA (SRSS+CQC) + Newmark time-history (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/load_combinations.py"

  # ── D3 Machine elements ───────────────────────────────────────────────────
  - domain: D3
    feature: "Spur/helical gear rating (AGMA 2001-D04)"
    competitor:
      status: partial
      note: "Creo includes gear geometry generators; no AGMA 2001-D04 rating engine in base product"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "Full AGMA 2001-D04 rating (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gears.py"

  - domain: D3
    feature: "Gear rating (ISO 6336)"
    competitor:
      status: partial
      note: "No native ISO 6336 rating; KISSsoft integration via partner ecosystem"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Method B + safety factors; ZH=2.495, ZE=191 √MPa validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gears.py"

  - domain: D3
    feature: "Bearings — ISO 281 L10"
    competitor:
      status: partial
      note: "Creo has bearing geometry generators; no ISO 281 L10 life calculation built in"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/part_modeling_intro.html"
    kerf:
      status: yes
      note: "ISO 281 L10 + ISO/TS 16281 aISO modified life (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  - domain: D3
    feature: "Fasteners — VDI 2230"
    competitor:
      status: no
      note: "No native VDI 2230 bolted-joint calculation in Creo"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "VDI 2230 bolted-joint design (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D3
    feature: "Springs (compr/ext/torsion/Belleville)"
    competitor:
      status: no
      note: "No spring design calculator in Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Compression/extension/torsion/Belleville (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D3
    feature: "Shaft (stress + critical speed)"
    competitor:
      status: no
      note: "No closed-form shaft design or critical-speed calculator in Creo"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Closed-form stress + critical speed (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  # ── D7 Manufacturing / CAM ───────────────────────────────────────────────
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: paid
      note: "Creo NC (Creo Milling/Turning/Mill-Turn) — mature 3-axis CAM, sold as separate module"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: yes
      note: "3-axis CAM + tool DB wired in CAMView"
      evidence: "packages/kerf-cam/src/kerf_cam/routes.py"

  - domain: D7
    feature: "5-axis (kinematics + posts)"
    competitor:
      status: paid
      note: "Creo NC Advanced — 5-axis machining + multi-axis toolpath verification"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: partial
      note: "5-axis engine solid; no UI; kinematics + posts (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/worker.py"

  - domain: D7
    feature: "Turning cycles (G71/G70/threading)"
    competitor:
      status: paid
      note: "Creo NC Turning — full turning cycle support with canned cycles"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: yes
      note: "G71/G70 roughing + threading cycles (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/routes.py"

  - domain: D7
    feature: "Feeds & speeds + tool-life"
    competitor:
      status: paid
      note: "Creo NC — feeds and speeds database with Taylor tool-life model"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: yes
      note: "Taylor extended (vcT^n·f^a·dp^b=C) + Gilbert economic speed (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/tool_db.py"

  - domain: D7
    feature: "Adaptive / trochoidal clearing"
    competitor:
      status: paid
      note: "Creo NC — HSM trochoidal and adaptive strategies in advanced module"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: yes
      note: "Iterative offset + 50% trochoid overlap; engagement on target (backend)"
      evidence: "packages/kerf-cam/src/kerf_cam/adaptive.py"

  - domain: D7
    feature: "G-code post (Fanuc/GRBL/LinuxCNC/Mach3)"
    competitor:
      status: paid
      note: "Creo NC — post-processor framework for Fanuc and others via customisable posts"
      source: "https://www.ptc.com/en/products/creo/options/nc"
    kerf:
      status: yes
      note: "Fanuc/GRBL/LinuxCNC/Mach3 posts; no G41/42 cutter-comp"
      evidence: "packages/kerf-cam/src/kerf_cam/posts/fanuc_3x.py"

  - domain: D7
    feature: "Moldflow / fill sim"
    competitor:
      status: paid
      note: "Creo Mold Analysis — basic fill sim; deeper analysis requires Moldflow integration"
      source: "https://www.ptc.com/en/products/creo/options/mold-analysis"
    kerf:
      status: yes
      note: "Hele-Shaw front tracking + weld-line + air-trap detection (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/flow_front.py"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: no
      note: "No nesting engine in Creo; requires third-party tools (e.g. Alma, Radan)"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Minkowski-sum NFP + IFP + bottom-left fill; 57.6% L-shape util (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/flow_front.py"

  - domain: D7
    feature: "FDM slicing (Cura)"
    competitor:
      status: no
      note: "No integrated FDM slicer in Creo; STL export + external slicer workflow required"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Cura slicer wired via PrintSliceView"
      evidence: "src/components/PrintSliceView.jsx"

  # ── D9 Dynamics / motion / controls ─────────────────────────────────────
  - domain: D9
    feature: "Kinematics (four-bar/slider-crank/cam)"
    competitor:
      status: yes
      note: "Creo Mechanism — full kinematic/dynamic simulation integrated in assembly"
      source: "https://www.ptc.com/en/products/creo/options/mechanism"
    kerf:
      status: yes
      note: "Planar four-bar/slider-crank/cam kinematics (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/joints.py"

  - domain: D9
    feature: "Planar MBD (Lagrange/DAE, Baumgarte)"
    competitor:
      status: yes
      note: "Creo Mechanism — rigid-body dynamics with joint motors, springs, gravity, and contacts"
      source: "https://www.ptc.com/en/products/creo/options/mechanism"
    kerf:
      status: yes
      note: "Lagrange/DAE + Baumgarte stabilisation (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/integrator.py"

  - domain: D9
    feature: "3D MBD with constraint enforcement"
    competitor:
      status: yes
      note: "Creo Mechanism supports full 3D rigid-body dynamics with constraint enforcement"
      source: "https://www.ptc.com/en/products/creo/options/mechanism"
    kerf:
      status: partial
      note: "Joints defined but 3D integrator unconstrained"
      evidence: "packages/kerf-motion/src/kerf_motion/joints.py"

  - domain: D9
    feature: "Controls — classical (Routh/Bode/RL/PID tune)"
    competitor:
      status: no
      note: "Creo has no control system analysis; requires MATLAB/Simulink co-simulation"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Routh/Bode/root-locus/PID auto-tune (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/tools.py"

  - domain: D9
    feature: "Controls — state-space / LQR / Kalman"
    competitor:
      status: no
      note: "No LQR or Kalman filter design in Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Ackermann + LQR (CARE) + Luenberger observer (backend)"
      evidence: "packages/kerf-motion/src/kerf_motion/tools.py"

  # ── D11 Tolerancing / metrology / QA ────────────────────────────────────
  - domain: D11
    feature: "GD&T data model (ASME Y14.5)"
    competitor:
      status: yes
      note: "Creo GD&T Advisor — automated GD&T rule validation per ASME Y14.5 / ISO 1101"
      source: "https://www.ptc.com/en/products/creo/options/gdt-advisor"
    kerf:
      status: yes
      note: "ASME Y14.5 datum + tolerance framework (backend; no MBD UI)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D11
    feature: "GD&T on drawings / MBD / PMI"
    competitor:
      status: paid
      note: "Creo MBD — 3D annotation planes, semantic PMI for paperless manufacturing (separate module)"
      source: "https://www.ptc.com/en/products/creo/options/mbd"
    kerf:
      status: partial
      note: "Data model only; no 3D MBD/PMI annotation UI"
      evidence: "src/components/DrawingView.jsx"

  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS/MC)"
    competitor:
      status: paid
      note: "Creo Design Exploration Extension + GD&T Advisor; no native 1D stackup engine in base Creo"
      source: "https://www.ptc.com/en/products/creo/options/design-exploration"
    kerf:
      status: yes
      note: "WC/RSS/Monte-Carlo stackup (backend; MC LCG bug known)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D11
    feature: "Tolerance stackup — 3D vector loop"
    competitor:
      status: paid
      note: "Creo Design Exploration Extension — sensitivity-based 3D tolerance analysis"
      source: "https://www.ptc.com/en/products/creo/options/design-exploration"
    kerf:
      status: yes
      note: "6-DOF vector loop + sensitivity Jacobian (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D11
    feature: "Limits & fits (ISO 286)"
    competitor:
      status: partial
      note: "No native ISO 286 limits-and-fits calculator; relies on GD&T Advisor tolerance selection"
      source: "https://www.ptc.com/en/products/creo/options/gdt-advisor"
    kerf:
      status: yes
      note: "Full ISO 286 H/h system calculator (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  - domain: D11
    feature: "Process capability (Cpk/Ppk)"
    competitor:
      status: no
      note: "No Cpk/Ppk process capability analysis in Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Cpk/Ppk + SPC control charts + Nelson/WECO rules (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core"

  # ── D13 Verticals ────────────────────────────────────────────────────────
  - domain: D13
    feature: "Generative design / topology optimisation"
    competitor:
      status: paid
      note: "Creo Generative Design Extension — cloud topology optimisation with manufacturing constraints"
      source: "https://www.ptc.com/en/products/creo/options/generative-design"
    kerf:
      status: yes
      note: "SIMP topology optimisation agent (backend)"
      evidence: "packages/kerf-fem/src/kerf_fem"

  - domain: D13
    feature: "Jewelry (41 modules)"
    competitor:
      status: no
      note: "No jewelry design tooling in Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Deep 41-module jewelry suite — ring/gem/setting/chain/casting; UI wired"
      evidence: "src/components/JewelryView.jsx"

  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: no
      note: "Creo is mechanical MCAD; no BIM workflow or IFC support"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Revit-comparable engine + viewer via /compile-ifc"
      evidence: "packages/kerf-bim/src/kerf_bim"

  # ── D6 Electronics / EDA ────────────────────────────────────────────────
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: no
      note: "Creo is a mechanical CAD tool; no native PCB schematic capture"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Schematic capture + KiCad round-trip viewer wired"
      evidence: "packages/kerf-electronics/src/kerf_electronics/schematic/capture.py"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: no
      note: "No PCB layout in Creo Parametric; ECAD/MCAD collaboration via ECAD Bridge add-on only"
      source: "https://www.ptc.com/en/products/creo/options/ecad-mcad-collaboration"
    kerf:
      status: yes
      note: "PCB viewer + KiCad round-trip wired (read-only)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/fab"

  - domain: D6
    feature: "SPICE simulation"
    competitor:
      status: no
      note: "No SPICE engine in Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Real ngspice wired; binary .raw parse gap noted"
      evidence: "packages/kerf-electronics/src/kerf_electronics/routes_spice.py"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No SI analysis in Creo; requires third-party EDA tools"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "IBIS 5.1 + Bergeron channel + PRBS eye envelope (backend)"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si"

  - domain: D6
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: paid
      note: "Creo Cabling — 3D harness routing integrated in assembly model (separate paid module)"
      source: "https://www.ptc.com/en/products/creo/options/cabling"
    kerf:
      status: yes
      note: "WiringView wired; harness3d 3D router + formboard + report"
      evidence: "packages/kerf-wiring/src/kerf_wiring"

  # ── D14 Cost / materials / LCA ───────────────────────────────────────────
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "No manufacturing cost estimation built into Creo Parametric"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "6 processes + Boothroyd-Dewhurst should-cost (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: partial
      note: "Creo has a material library for density/modulus/yield; no Pareto/Ashby multi-objective selection"
      source: "https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/index.html#page/part_modeling/materials/materials_intro.html"
    kerf:
      status: yes
      note: "200 materials, Pareto frontier, weighted-score (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca"

  - domain: D14
    feature: "LCA (full ISO 14040/44 4 phases)"
    competitor:
      status: no
      note: "No LCA or environmental impact assessment in Creo"
      source: "https://www.ptc.com/en/products/creo/parametric"
    kerf:
      status: yes
      note: "Use+transport+EoL + multi-impact categories (ISO 14040/44; backend)"
      evidence: "packages/kerf-lca/src/kerf_lca"
---

# Kerf vs PTC Creo

PTC Creo (formerly Pro/ENGINEER) invented parametric feature-based solid modelling in 1988 and has shaped how the entire CAD industry thinks about design intent, feature trees, and bidirectional associativity. It remains one of the most widely used mechanical CAD platforms in manufacturing, with particular strength in sheet metal, piping, and model-based definition (MBD). Creo Parametric is PTC's flagship; the platform extends to Creo Simulate (FEM), Creo Illustrate, and Creo View. Pricing is enterprise-level. Kerf is the MIT-licensed alternative for teams doing serious parametric mechanical work without the subscription.

## Where they converge

Both Creo and Kerf are built on parametric B-rep feature trees with constraint-based sketchers. Both produce associative drawings (change the model, the drawing updates). Both treat geometric precision as non-negotiable — tolerances, manufacturing constraints, and GD&T are first-class, not bolt-ons. Both handle sheet metal as a genuine manufacturing workflow: flanges, bends, unfold, flat pattern, and DXF export.

Both tools also acknowledge multi-disciplinary reality. Creo spans mechanical, simulation, technical illustration, and AR/VR output; Kerf spans mechanical, electronics, scripting, and a cloud collaboration layer. The ambition to cover the full engineering workflow — not just geometry — is shared.

## Where Kerf wins

- **MIT open-core, no subscription.** Creo Parametric starts at thousands of dollars per seat per year (as of May 2026) and escalates quickly with modules (Simulate, Advanced Assembly, Surfacing). Kerf's full feature set is MIT-licensed — free locally, no seat fee, no module gating.
- **Chat-native workflow.** Describe a design change in plain language and the LLM edits the feature tree, backed by live doc-search so it does not hallucinate API surface. No LLM interface in Creo has shipped to our knowledge (as of May 2026).
- **In-box electronics.** Creo is a mechanical tool. Kerf ships PCB schematic, layout, pre-compliance simulation (SI/EMC/PDN/thermal), and full fab output without extension gating. For hardware products that include a PCB, Kerf is a single workspace.
- **Single-binary install, all platforms.** A brew or curl install on macOS, Windows, or Linux gives a fully functional offline binary. Creo requires Windows and a PTC FlexNet licence server.
- **BYO LLM key.** Bring your own Anthropic or OpenAI API key via the `kerf_byo` bucket. We're not aware of any configurable AI interface in Creo (as of May 2026).

## Where Creo wins

- **Decades of field validation.** Pro/ENGINEER and its successors have powered real production manufacturing for 35+ years. The feature modelling reliability, fillets-on-fillets handling, and large-assembly performance have been hardened against real-world failure modes that Kerf's younger kernel has not encountered.
- **Creo Simulate (Mechanica).** Built-in structural, thermal, and fatigue FEM with h-element adaptive meshing — a mature simulation capability Kerf does not ship.
- **Piping and cabling.** Creo Piping and Cabling workbenches route rigid pipe, flex hose, and electrical harnesses within the assembly model. Kerf has no equivalent.
- **Model-based definition (MBD).** Creo GD&T Advisor and 3D annotation planes produce fully annotated 3D models for paperless manufacturing — a standard Kerf's drawing layer does not yet match in depth.
- **Large-assembly performance.** Creo has been engineered to handle assemblies of thousands of components in simplified representation mode. Kerf's assembly layer is newer.

## Feature matrix

| Feature | Kerf | PTC Creo Parametric |
|---|---|---|
| License | MIT open-core | Proprietary subscription |
| Cost | Free local; hosted credits | Thousands USD/seat/yr + modules (May 2026) |
| OS support | Win / macOS / Linux (browser + binary) | Windows only (desktop) |
| B-rep kernel | Open CASCADE (OCCT) | PTC's Granite One kernel |
| Parametric history | Feature DAG | Feature tree (industry pioneer) |
| Constraint sketcher | Sketcher v2 | Creo Sketcher (mature) |
| Sheet metal | Flange + unfold + flat-pattern DXF | Sheet Metal workbench (mature) |
| Surfacing | NURBS Phase 4 (early) | Style / ISDX surfacing |
| Assembly | Assembly mates | Full assembly + large-assembly management |
| FEM / structural | Not yet | Creo Simulate (Mechanica, mature) |
| Piping / cabling | Not yet | Piping + Cabling workbenches |
| MBD / 3D annotation | GD&T drawings | Creo MBD + GD&T Advisor |
| PCB / electronics | In-box (full stack + pre-compliance) | Not included |
| Chat / LLM editing | Chat-native | None known (as of May 2026) |
| Python scripting | kerf-sdk on PyPI | Creo Toolkit (C++) / J-Link (Java) |
| STEP export | Yes | Yes |
| Open source | Yes (MIT) | No |

## Both produce STEP

Creo and Kerf both export ISO 10303 STEP (AP214 / AP242). STEP is the universal handshake in mechanical CAD. Geometry produced in Creo can be imported into Kerf for downstream PCB integration, scripted analysis, or cloud collaboration — and vice versa.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public PTC product pages. Kerf capabilities reflect the current shipped product.*
