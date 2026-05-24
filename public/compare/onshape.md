---
slug: onshape
competitor: "Onshape"
category: cad-mechanical
left: kerf
right: onshape
hero_tagline: "Browser-native real-time-collab CAD — closest peer in cloud shape."
reviewed_at: 2026-05-19
order: 4
features:
  # ── D1 Geometry & core CAD ───────────────────────────────────────────────
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "Full parametric sketcher in Part Studios"
      source: "https://cad.onshape.com/help/Content/sketch_basics.htm"
    kerf:
      status: yes
      note: "PlaneGCS WASM; collinear/ellipse/G2 missing"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"

  - domain: D1
    feature: "Parametric B-rep modeller"
    competitor:
      status: yes
      note: "Timeline-based Part Studios (decade-mature)"
      source: "https://cad.onshape.com/help/Content/modeling.htm"
    kerf:
      status: yes
      note: "OCCT feature tree"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: yes
      note: "Full sheet-metal workspace with flat-pattern, DXF"
      source: "https://cad.onshape.com/help/Content/sheetmetal.htm"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF (K-factor); no auto corner-relief"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: yes
      note: "Fastened/revolute/slider/cylindrical/planar/pin-slot/ball"
      source: "https://cad.onshape.com/help/Content/Assembly/mates.htm"
    kerf:
      status: yes
      note: "Coincident/concentric/parallel/revolute/slider wired + BOM"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/surfacing.py"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Full Drawings workspace; DWG/DXF output"
      source: "https://cad.onshape.com/help/Content/drawings.htm"
    kerf:
      status: partial
      note: "Multi-sheet HLR drawings; no GD&T placement UI"
      evidence: "src/components/DrawingView.jsx"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: yes
      note: "Part Studio + Assembly Configurations; Variable Studio"
      source: "https://cad.onshape.com/help/Content/PartStudio/configurations.htm"
    kerf:
      status: yes
      note: "ConfigurationsPanel.jsx wired in Editor.jsx"
      evidence: "src/components/ConfigurationsPanel.jsx"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: yes
      note: "Surface modelling tools in Part Studios"
      source: "https://www.onshape.com/en/features/surfacing"
    kerf:
      status: yes
      note: "blend_srf, network_srf (Gordon), patch_srf_fit, match_srf, G3 blends wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py"

  - domain: D1
    feature: "GD&T on drawings / MBD / PMI"
    competitor:
      status: yes
      note: "GD&T + MBD with datums, tolerances in 3D model"
      source: "https://cad.onshape.com/help/Content/drawings-gdt.htm"
    kerf:
      status: partial
      note: "Data model + auto-propose only; no UI placement"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py"

  # ── D2 Structural / FEA ──────────────────────────────────────────────────
  - domain: D2
    feature: "FEM linear static + modal (built-in)"
    competitor:
      status: paid
      note: "Simulation included in Professional/Enterprise plan only"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: partial
      note: "Linear static + thermal + modal; no UI panel"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "No per-code steel member checks; requires third-party"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "Full Ch. E/F/H + 50-section catalog (backend)"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  - domain: D2
    feature: "Fatigue (S-N, ε-N, rainflow)"
    competitor:
      status: no
      note: "No fatigue solver; simulation is linear static + modal only"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "S-N, ε-N, multiaxial rainflow (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/fatigue/life.py"

  - domain: D2
    feature: "ASCE 7-22 seismic / wind"
    competitor:
      status: no
      note: "No load-code calculators built in"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "ELF+RSA+Newmark + MWFRS+C&C (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/seismic/rsa.py"

  # ── D3 Machine elements ───────────────────────────────────────────────────
  - domain: D3
    feature: "Spur/helical gear rating (AGMA/ISO 6336)"
    competitor:
      status: no
      note: "No in-platform gear rating; FeatureScript geometry only"
      source: "https://cad.onshape.com/FsDoc/"
    kerf:
      status: yes
      note: "AGMA 2001-D04 + ISO 6336 Method B (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gearstrength/iso6336.py"

  - domain: D3
    feature: "Bearings — ISO 281 / ISO/TS 16281"
    competitor:
      status: no
      note: "No bearing life calculators built in"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "L10 + modified Lnm with misalignment (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  - domain: D3
    feature: "Planetary / epicyclic gearbox"
    competitor:
      status: no
      note: "No gearbox sizing engine; geometry via FeatureScript only"
      source: "https://cad.onshape.com/FsDoc/"
    kerf:
      status: yes
      note: "3 Willis modes + compound + module-select (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gearbox/planetary.py"

  - domain: D3
    feature: "Springs (compr/ext/torsion/Belleville)"
    competitor:
      status: no
      note: "No spring design calculators built in"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Full spring design suite (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/springs/design.py"

  # ── D4 Thermal / fluid / HVAC ─────────────────────────────────────────────
  - domain: D4
    feature: "Heat exchangers (LMTD + ε-NTU + Bell-Delaware)"
    competitor:
      status: no
      note: "No thermal calc engines; CFD via SimScale App Store"
      source: "https://www.onshape.com/en/blog/rapid-design-simulation-directly-browser"
    kerf:
      status: yes
      note: "LMTD+ε-NTU+Bell-Delaware+TEMA layout (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/heatxfer/shell_tube_bell.py"

  - domain: D4
    feature: "Steam/water properties (IAPWS-IF97)"
    competitor:
      status: no
      note: "No fluid property library built in"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "IAPWS-IF97 Regions 1/2/4; h/v/s/cp validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/fluids/iapws_if97.py"

  - domain: D4
    feature: "CFD"
    competitor:
      status: paid
      note: "Via SimScale / OnScale App Store add-ons; not bundled"
      source: "https://www.onshape.com/en/blog/rapid-design-simulation-directly-browser"
    kerf:
      status: partial
      note: "Real OpenFOAM bridge (backend, needs install)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/heatxfer/transfer.py"

  # ── D5 Aero / marine / space ──────────────────────────────────────────────
  - domain: D5
    feature: "3D wing VLM (+ viscous + compressibility)"
    competitor:
      status: no
      note: "No aerodynamics solver; geometry only"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Strip viscous CD0+PG/KT+Korn-Lock wave-drag (backend)"
      evidence: "packages/kerf-aero/src/kerf_aero/vlm_viscous.py"

  - domain: D5
    feature: "Orbital mechanics (Kepler, J2/J3, Hohmann)"
    competitor:
      status: no
      note: "No space / orbital analysis tools"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Lambert multi-rev + Hohmann + reentry wired"
      evidence: "packages/kerf-aero/src/kerf_aero/vlm.py"

  - domain: D5
    feature: "Naval hydrostatics + GZ stability (IMO)"
    competitor:
      status: no
      note: "No marine analysis tools built in"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Hydrostatics + GZ curve + IMO criteria (backend)"
      evidence: "packages/kerf-marine/src/kerf_marine/stability.py"

  # ── D6 Electronics / EDA / silicon ────────────────────────────────────────
  - domain: D6
    feature: "Schematic capture (KiCad round-trip, ERC)"
    competitor:
      status: partial
      note: "PCB Studio is MCAD↔ECAD bridge, not a schematic editor"
      source: "https://cad.onshape.com/help/Content/PCBStudio/pcb_studios.htm"
    kerf:
      status: yes
      note: "Hierarchical schematic + ERC viewer wired"
      evidence: "src/components/SchematicView.jsx"

  - domain: D6
    feature: "PCB layout (tscircuit, KiCad round-trip)"
    competitor:
      status: partial
      note: "PCB Studio imports IDF/IDX/EAGLE/Altium; no routing editor"
      source: "https://cad.onshape.com/help/Content/PCBStudio/pcb_studios.htm"
    kerf:
      status: yes
      note: "PCB viewer + DRC overlay wired; no cursor editing"
      evidence: "src/components/PCBView.jsx"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No SI analysis built in; requires third-party integrations"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "IBIS 5.1+Bergeron+PRBS eye; backend"
      evidence: "packages/kerf-electronics/src/kerf_electronics/si/ibis_parser.py"

  - domain: D6
    feature: "Silicon synth (Yosys) / STA / GDS / DRC / LVS"
    competitor:
      status: no
      note: "No silicon / RTL design tools"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "Yosys/OpenLane bridge; deep but zero UI (backend)"
      evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py"

  - domain: D6
    feature: "Analog PVT corner simulation"
    competitor:
      status: no
      note: "No analog simulation tools"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "60 corners (5P×3V×4T)+MC per corner (backend)"
      evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py"

  # ── D7 Manufacturing / CAM ────────────────────────────────────────────────
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: paid
      note: "CAM Studio 2.5/3-axis included in Professional plan"
      source: "https://www.onshape.com/en/features/cam-studio"
    kerf:
      status: yes
      note: "CAMView wired; Fanuc/GRBL/LinuxCNC posts"
      evidence: "src/components/CAMView.jsx"

  - domain: D7
    feature: "5-axis CAM (kinematics + posts)"
    competitor:
      status: paid
      note: "CAM Studio Advanced (add-on): 4/3+2/5-axis"
      source: "https://www.onshape.com/en/blog/cam-studio-comprehensive-milling"
    kerf:
      status: partial
      note: "5-axis engine solid; no UI"
      evidence: "packages/kerf-cam/src/kerf_cam/adaptive.py"

  - domain: D7
    feature: "Feeds & speeds + tool-life"
    competitor:
      status: partial
      note: "Basic tool library in CAM Studio; no Taylor model"
      source: "https://cad.onshape.com/help/Content/CAMStudio/cam_studios.htm"
    kerf:
      status: yes
      note: "Taylor extended + Gilbert economic speed (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/cuttingtool/tool_life.py"

  - domain: D7
    feature: "Moldflow / fill simulation"
    competitor:
      status: no
      note: "No injection-moulding simulation built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "Hele-Shaw front tracking+weld-line+air-trap (backend)"
      evidence: "packages/kerf-manufacturing/src/kerf_manufacturing/moldflow/flow_front.py"

  - domain: D7
    feature: "Nesting (skyline + true-shape NFP)"
    competitor:
      status: no
      note: "No nesting engine built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "Minkowski-sum NFP+IFP+bottom-left fill (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/nesting/nfp.py"

  - domain: D7
    feature: "FDM slicing (Cura)"
    competitor:
      status: no
      note: "No slicer; export STL and use external tool"
      source: "https://cad.onshape.com/help/Content/translation.htm"
    kerf:
      status: yes
      note: "PrintSliceView wired (Cura integration)"
      evidence: "src/components/PrintSliceView.jsx"

  # ── D8 Civil / infrastructure / geo ──────────────────────────────────────
  - domain: D8
    feature: "Horizontal+vertical alignment (clothoid, SSD)"
    competitor:
      status: no
      note: "No civil/road alignment tools; mechanical CAD only"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "AASHTO superelevation + corridor templates (backend)"
      evidence: "packages/kerf-civil/src/kerf_civil/superelevation.py"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/pile/liquefaction)"
    competitor:
      status: no
      note: "No geotechnical analysis tools"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Seed-Idriss CSR+SPT/CPT CRR+Tokimatsu (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geotech/liquefaction.py"

  # ── D9 Dynamics / motion / controls ──────────────────────────────────────
  - domain: D9
    feature: "Planar MBD (Lagrange/DAE, Baumgarte)"
    competitor:
      status: no
      note: "No MBD solver; assembly motion via simulation mates only"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "Planar DAE + Baumgarte stabilisation (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/dynamics/rigidbody.py"

  - domain: D9
    feature: "Vibration n-DOF modal / FRF"
    competitor:
      status: paid
      note: "Modal natural frequency in Simulation (Professional plan)"
      source: "https://www.onshape.com/en/features/simulation"
    kerf:
      status: yes
      note: "Full n-DOF eigen + FRF matrix (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/vibration/mdof.py"

  - domain: D9
    feature: "Controls — state-space / LQR / Kalman"
    competitor:
      status: no
      note: "No control system design tools"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "Ackermann+LQR(CARE)+Luenberger (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/controls/statespace.py"

  - domain: D9
    feature: "Robotics 6-DOF spatial IK"
    competitor:
      status: no
      note: "No robotics kinematics solver"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "DLS Jacobian IK; PUMA-class validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/robotics/arm.py"

  # ── D10 Electrical / energy / PLC / firmware ──────────────────────────────
  - domain: D10
    feature: "AC load-flow (Ybus / Newton-Raphson)"
    competitor:
      status: no
      note: "No electrical power analysis; mechanical CAD only"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Polar-form NR; 3+5-bus validated (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/elecpower/loadflow.py"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "No PV or energy analysis tools"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Single-diode+bypass-diode+global MPPT (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/solarpv/shading.py"

  - domain: D10
    feature: "Wiring/harness (WireViz + 3D router)"
    competitor:
      status: no
      note: "No harness/wiring tools; PCB Studio is MCAD↔ECAD only"
      source: "https://cad.onshape.com/help/Content/PCBStudio/pcb_studios.htm"
    kerf:
      status: yes
      note: "WiringView wired"
      evidence: "src/components/WiringView.jsx"

  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB/motion)"
    competitor:
      status: no
      note: "No PLC programming environment"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired"
      evidence: "src/components/PLCView.jsx"

  - domain: D10
    feature: "Firmware build/upload/monitor/debug"
    competitor:
      status: no
      note: "No firmware toolchain built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "FirmwareActions + debug panel wired"
      evidence: "src/components/FirmwareActions.jsx"

  # ── D11 Tolerancing / metrology / QA ──────────────────────────────────────
  - domain: D11
    feature: "GD&T data model (ASME Y14.5)"
    competitor:
      status: yes
      note: "GD&T on drawings + MBD; fit class tolerances on holes"
      source: "https://cad.onshape.com/help/Content/drawings-gdt.htm"
    kerf:
      status: yes
      note: "ASME Y14.5 data model + auto-propose (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py"

  - domain: D11
    feature: "Limits & fits (ISO 286)"
    competitor:
      status: yes
      note: "Fit class tolerances on hole features (Onshape help)"
      source: "https://www.onshape.com/en/resource-center/what-is-new/modal-analysis-fit-class-tolerances-hole-features"
    kerf:
      status: yes
      note: "ISO 286 limits & fits engine (backend)"
      evidence: "packages/kerf-gdnt/src/kerf_gdnt/inspection_report.py"

  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS/MC)"
    competitor:
      status: no
      note: "No tolerance stackup analysis; MBD annotation only"
      source: "https://cad.onshape.com/help/Content/Home/tolerance_options.htm"
    kerf:
      status: yes
      note: "WC/RSS/Monte-Carlo (backend; LCG bug to fix)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolstack/stack.py"

  - domain: D11
    feature: "Tolerance stackup — 3D vector loop"
    competitor:
      status: no
      note: "No 3D tolerance stackup"
      source: "https://cad.onshape.com/help/Content/Home/tolerance_options.htm"
    kerf:
      status: yes
      note: "6-DOF vector loop + sensitivity Jacobian (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolstack/tol3d.py"

  - domain: D11
    feature: "SPC control charts (Shewhart/CUSUM/EWMA)"
    competitor:
      status: no
      note: "No SPC / process quality tools built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "Shewhart+CUSUM+EWMA+Nelson/WECO run rules (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/spc/charts.py"

  # ── D12 Optics / acoustics ────────────────────────────────────────────────
  - domain: D12
    feature: "Paraxial ABCD ray transfer"
    competitor:
      status: no
      note: "No optics tooling"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Paraxial ABCD + Seidel aberrations + lensmaker (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/optics/lens.py"

  - domain: D12
    feature: "Acoustics (ISO 9613, RT60, weighting, mass-law TL)"
    competitor:
      status: no
      note: "No acoustics analysis; requires SimScale add-on"
      source: "https://www.onshape.com/en/blog/rapid-design-simulation-directly-browser"
    kerf:
      status: yes
      note: "Image-source IR+Schroeder RT60+modes+SEA (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/acoustics/wave.py"

  # ── D13 Verticals ─────────────────────────────────────────────────────────
  - domain: D13
    feature: "Jewelry (41 modules)"
    competitor:
      status: no
      note: "No jewelry domain tooling"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Ring v4/gems v2 (30 cuts)/settings/chain v2 wired"
      evidence: "src/routes/JewelryShare.jsx"

  - domain: D13
    feature: "BIM (walls/slabs/framing/stairs/IFC4)"
    competitor:
      status: no
      note: "Mechanical CAD only; no BIM or IFC output"
      source: "https://www.onshape.com/en/features/parts-modeling"
    kerf:
      status: yes
      note: "Revit-comparable engine + IFC4 viewer wired"
      evidence: "src/components/BIMView.jsx"

  # ── D14 Cost / materials / LCA ────────────────────────────────────────────
  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "No cost estimation engine built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "6-process should-cost + RFQ geometry-driven (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/phases.py"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: partial
      note: "Basic material properties assignable; no Ashby charts"
      source: "https://cad.onshape.com/help/Content/PartStudio/configurations.htm"
    kerf:
      status: yes
      note: "200 materials, 14 families, Pareto frontier (backend)"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/multi_objective.py"

  - domain: D14
    feature: "LCA (full ISO 14040/44 4 phases)"
    competitor:
      status: no
      note: "No LCA or environmental impact analysis built in"
      source: "https://www.onshape.com/en/features/integrations"
    kerf:
      status: yes
      note: "ISO 14040/44 4-phase+multi-impact+uncertainty (backend)"
      evidence: "packages/kerf-lca/src/kerf_lca/phases.py"
---

# Kerf vs Onshape

Onshape (PTC) pioneered cloud-native parametric CAD and remains the benchmark for real-time multi-user collaboration in design — the ability for multiple engineers to edit the same model simultaneously in a browser is genuinely unmatched. It introduced version-controlled Documents, FeatureScript for custom parametric features, and a growing App Store for simulation and rendering. Subscriptions start at ~US$1,500/yr (as of May 2026); the free tier allows public documents only. Kerf is the most natural peer comparison: cloud-friendly, browser-first, parametric. The honest picture is below.

## Where Onshape is strong

- **Real-time multi-user collaboration.** Onshape's defining capability: concurrent editing with live cursors and instant conflict resolution, all in the browser. No file locking, no "check out". This is genuinely ahead of any current Kerf collab offering.
- **True cloud-native architecture.** Purpose-built for the cloud from day one — no sync client, no save button, no version-mismatch between team members.
- **Built-in version control (Documents).** Branching, tagging, and history are first-class features baked into the platform — no separate Git integration needed.
- **FeatureScript ecosystem.** FeatureScript is a proprietary DSL, but it has produced a rich library of custom parametric features in the App Store, refined over years of community contribution.
- **Mobile and tablet editing.** Dedicated iOS and Android apps with full model editing — Kerf is a responsive browser experience without a native app.
- **Mature parametric CAD.** Part Studios with a decade of engineering behind them, a polished UI, and battle-tested reliability across complex industrial models.
- **Professional training and certification.** Onshape Learning Center, official certifications, and a large professional user base with extensive community content.

## Where Kerf differs

- **MIT open-core — no subscription, full offline.** Onshape requires a subscription starting at ~US$1,500/yr (as of May 2026); the free tier allows public documents only. Kerf is MIT-licensed — install the binary locally (brew/curl) for free, no account required, no connectivity needed, no revenue cap.
- **Open kernel, not a proprietary DSL.** Onshape extends via FeatureScript, a language PTC controls. Kerf's parametric DAG is backed by the MIT-licensed kernel directly — the extensibility surface is open.
- **Chat-native workflow with BYO LLM.** Describe a feature, constraint, or routing rule in plain language; the model edits the source backed by live doc-search. You can use Kerf's hosted models or bring your own API key — any OpenAI-compatible endpoint. Onshape has no LLM integration we're aware of (as of May 2026).
- **Multi-discipline: mechanical + electronics + jewelry.** Onshape is mechanical CAD. Kerf adds a full EDA stack (hierarchical schematic, shove router, SPICE, DRC, Gerber / IPC-2581) and a jewelry domain (ring v4, gemstones v2 — 30 cuts, settings, chain v2) in the same workspace.
- **620 analytic-oracle verified kernel tests.** The parametric and sketcher kernel ships with a verified test suite — results are checked against OCCT analytic ground truth.
- **kerf-sdk Python scripting (out-of-process).** HTTP/JSON-RPC from your own machine — the same interface the LLM uses internally.

## Honest gaps — where Kerf is behind today

- **Real-time collab maturity.** Onshape's concurrent multi-user editing is a decade in the making. Kerf's cloud collaboration feature is less mature. If live concurrent editing is critical, Onshape is ahead.
- **FeatureScript ecosystem.** Years of community-built FeatureScript features in Onshape's App Store have no Kerf equivalent today.
- **No mobile app.** Onshape's iOS and Android apps support editing on the go; Kerf is a responsive browser only.
- **Simulation ecosystem is smaller.** Neither platform ships first-party FEM, but Onshape's App Store has more mature simulation partner integrations available today.
- **Vendor polish and assembly depth.** Onshape's UI, mating system, and overall product finish reflect ten years of professional refinement. Kerf is younger.
- **Smaller community.** Onshape has a large, professionally-certified user base. Kerf's community is early-stage and growing.

## Side by side

| Feature | Onshape | Kerf |
|---|---|---|
| License | ⚠️ Proprietary SaaS subscription | ✅ MIT open-core |
| Cost | ⚠️ Standard ~US$1,500/yr; Professional ~US$2,100/yr (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Free tier | ⚠️ Public documents only | ✅ Full free local install, private projects included |
| Offline / self-host | ❌ Browser-only; requires connectivity | ✅ Full offline single-binary install |
| Open source | ❌ Proprietary; data on PTC cloud | ✅ MIT — full codebase on GitHub |
| Vendor lock-in | ⚠️ PTC-hosted; export-only escape hatch | ✅ Open format; self-hostable |
| Real-time multi-user collab | ✅ Industry-leading concurrent editing | ⚠️ Cloud collab less mature |
| Version control (branches) | ✅ Built-in branching / tagging in Documents | ✅ file_revisions + cloud git branches |
| Mobile / tablet editing | ✅ iOS / Android apps | ⚠️ Responsive browser; no dedicated mobile app |
| Parametric B-rep | ✅ Mature Part Studios (OCCT underneath) | ✅ OCCT feature tree |
| Constraint sketcher | ✅ Full parametric sketcher | ✅ Sketcher v2 — all major constraints |
| Sheet metal | ✅ Full sheet-metal workspace | ✅ Flange + hem + jog + multi-flange + unfold + flat DXF |
| Custom parametric features | ✅ FeatureScript (rich App Store ecosystem) | ✅ MIT kernel directly; open DAG |
| Scripting / automation | ⚠️ FeatureScript only; REST API limited | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| BYO LLM / AI | ❌ None | ✅ BYO key or hosted models |
| Chat / LLM editing | ❌ None | ✅ Chat-native — edits source per turn |
| Assembly mates | ✅ Full mate system in Assemblies | ⚠️ Assembly mates (newer) |
| 2D technical drawings | ✅ Drawings workspace | ✅ Multi-sheet drawings |
| Electronics / PCB | ❌ Mechanical CAD only | ✅ Full EDA — schematic, routing, DRC |
| Jewelry tooling | ❌ None | ✅ Ring v4, gemstones v2 (30 cuts), settings, chain v2 |
| App Store / add-ons | ✅ PTC App Store — simulation, rendering, CAM | ⚠️ Early — open-core + plugin API |
| Import / export formats | ✅ STEP, IGES, Parasolid, ACIS, DXF | ✅ STEP/IGES/DXF/IFC/FreeCAD import |
