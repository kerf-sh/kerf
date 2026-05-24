---
slug: solidworks
competitor: "SOLIDWORKS"
category: cad-mechanical
left: kerf
right: solidworks
hero_tagline: "30 years of Parasolid-kernel polish — compared honestly against MIT open-core."
reviewed_at: 2026-05-19
order: 3
features:
  # ── D1 Geometry & core CAD ────────────────────────────────────────────────
  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: yes
      note: "Full parametric sketcher; all standard geometric + dimensional constraints"
      source: "https://help.solidworks.com/2022/English/SolidWorks/sldworks/t_Defining_Constraints.htm"
    kerf:
      status: yes
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/sketch.py"

  - domain: D1
    feature: "Pad / pocket / revolve"
    competitor:
      status: yes
      note: "Extrude/Cut/Revolve as base and boss features"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: yes
      note: "OCCT, wired in browser"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/analysis.py"

  - domain: D1
    feature: "Fillet / chamfer (constant)"
    competitor:
      status: yes
      note: "Standard constant-radius fillet and chamfer"
      source: "https://help.solidworks.com/2022/english/SolidWorks/sldworks/r_Variable_Size_Fillet.htm"
    kerf:
      status: yes
      note: "Wired via OCCT"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/analysis.py"

  - domain: D1
    feature: "Variable-radius fillet"
    competitor:
      status: yes
      note: "Variable size fillets with control-point radius assignment"
      source: "https://help.solidworks.com/2022/english/SolidWorks/sldworks/r_Variable_Size_Fillet.htm"
    kerf:
      status: yes
      note: "Wired; runtime-probed law binding"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/analysis.py"

  - domain: D1
    feature: "Sweep (1 & 2 rail)"
    competitor:
      status: yes
      note: "Guide-curve sweeps with twist control"
      source: "https://help.solidworks.com/2021/English/SolidWorks/sldworks/hidd_dve_feat_sweep.htm"
    kerf:
      status: yes
      note: "BRepOffsetAPI_MakePipeShell"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/analysis.py"

  - domain: D1
    feature: "Sheet metal"
    competitor:
      status: yes
      note: "Full sheet-metal workbench; flange, hem, relief, jog, flat-pattern DXF"
      source: "https://help.solidworks.com/2026/English/SolidWorks/sldworks/t_Creating_Sheet_Metal_Flat_Pattern_Configurations.htm"
    kerf:
      status: yes
      note: "Flange + hem + jog + multi-flange + unfold + flat DXF + bend table; no auto corner-relief"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py"

  - domain: D1
    feature: "NURBS surfacing (blend/network/patch)"
    competitor:
      status: yes
      note: "Full surface workbench in all tiers; Class-A via Premium"
      source: "https://help.solidworks.com/2024/english/solidworks/sldworks/c_Surfaces_Overview.htm"
    kerf:
      status: yes
      note: "blend/network/patch/match-srf + G3 blends + Class-A continuity harness wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: yes
      note: "Full mate system: coincident/concentric/gear/cam/screw/slot"
      source: "https://help.solidworks.com/2025/English/SolidWorks/sldworks/c_Mechanical_Mates.htm"
    kerf:
      status: yes
      note: "Rigid/revolute/slider/cam/gear/pin-slot wired + BOM panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/mates.py"

  - domain: D1
    feature: "Assembly interference (clash)"
    competitor:
      status: yes
      note: "Motion Studies check interference as parts move"
      source: "https://help.solidworks.com/2024/english/SolidWorks/motionstudies/t_detecting_interference_motion.htm"
    kerf:
      status: partial
      note: "Backend OBB-SAT + BVH + tri-tri; no UI panel"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/clash/detect.py"

  - domain: D1
    feature: "Assembly motion study"
    competitor:
      status: yes
      note: "Motion analysis with contacts, cam followers, interference detection"
      source: "https://help.solidworks.com/2025/english/SolidWorks/motionstudies/t_detecting_interference_motion.htm"
    kerf:
      status: no
      note: "Planar MBD not wired to assembly solver"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/model.py"

  - domain: D1
    feature: "2D drawings (views/dims/sections)"
    competitor:
      status: yes
      note: "Full drawing environment; views, dimensions, section views"
      source: "https://help.solidworks.com/2024/english/SolidWorks/acadhelp/c_drawing_views_acadhelp.htm"
    kerf:
      status: partial
      note: "Live B-rep HLR projection + auto-dim; no GD&T-placement UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/drawings/auto_dimension.py"

  - domain: D1
    feature: "GD&T on drawings / MBD / PMI"
    competitor:
      status: yes
      note: "DimXpert per ASME Y14.41/ISO 16792; MBD annotation"
      source: "https://help.solidworks.com/2020/English/SolidWorks/sldworks/c_dimxpert_for_parts.htm"
    kerf:
      status: partial
      note: "Data model + auto-propose only; no UI for placement"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gdt/tools.py"

  - domain: D1
    feature: "Configurations / family variants"
    competitor:
      status: yes
      note: "Configurations manager; design tables for parameter families"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_Configurations_Overview.htm"
    kerf:
      status: yes
      note: "Engine + ConfigurationsPanel.jsx wired in Editor.jsx"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/family/model.py"

  - domain: D1
    feature: "Large assembly performance mode"
    competitor:
      status: yes
      note: "SpeedPak configurations, lightweight component loading"
      source: "https://help.solidworks.com/2025/English/SolidWorks/sldworks/c_SpeedPak_OH.htm"
    kerf:
      status: partial
      note: "LOD mesh swapping (configurable); no SpeedPak equivalent"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/assembly/perf.py"

  # ── D2 Structural / FEA ───────────────────────────────────────────────────
  - domain: D2
    feature: "FE — linear static (native)"
    competitor:
      status: yes
      note: "SOLIDWORKS Simulation Standard — linear static study"
      source: "https://help.solidworks.com/2021/english/SolidWorks/cworks/c_Fatigue_Analysis.htm"
    kerf:
      status: partial
      note: "Linear static solver; no UI panel beyond displacement render"
      evidence: "packages/kerf-fem/src/kerf_fem/linear_static.py"

  - domain: D2
    feature: "FE — fatigue (S-N)"
    competitor:
      status: paid
      note: "SOLIDWORKS Simulation Professional and Premium; not Standard"
      source: "https://help.solidworks.com/2024/english/SolidWorks/cworks/c_Fatigue_Analysis.htm"
    kerf:
      status: partial
      note: "S-N + ε-N + rainflow backend; no UI"
      evidence: "packages/kerf-fem/src/kerf_fem/fatigue_fem.py"

  - domain: D2
    feature: "Modal / buckling / nonlinear FEA"
    competitor:
      status: paid
      note: "Frequency/buckling in Simulation Standard; nonlinear in Premium"
      source: "https://help.solidworks.com/2026/english/simtutorialonline/c_simconn_fatigue.htm"
    kerf:
      status: partial
      note: "Consistent-mass modal + Riks + J2 plasticity backend"
      evidence: "packages/kerf-fem/src/kerf_fem/modal.py"

  - domain: D2
    feature: "AISC 360 / ACI 318 member design"
    competitor:
      status: no
      note: "No code-check calculators in SOLIDWORKS base product"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Full per-code backend; no UI panel"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  # ── D3 Machine elements ───────────────────────────────────────────────────
  - domain: D3
    feature: "Spur/helical gear rating (AGMA/ISO 6336)"
    competitor:
      status: no
      note: "Gear mates for motion only; no AGMA/ISO strength rating in base SW"
      source: "https://help.solidworks.com/2024/English/SolidWorks/sldworks/t_Gear_Mates_SWassy.htm"
    kerf:
      status: partial
      note: "Full AGMA 2001-D04 + ISO 6336 Method B backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gearstrength/iso6336.py"

  - domain: D3
    feature: "Bearings — ISO 281 L10 / ISO/TS 16281"
    competitor:
      status: no
      note: "Bearing loads as FEA BC only; no catalogue life rating"
      source: "https://help.solidworks.com/2021/english/SolidWorks/cworks/c_Bearing_Loads.htm"
    kerf:
      status: partial
      note: "ISO 281 + ISO/TS 16281 aISO modified life backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/bearings/select.py"

  - domain: D3
    feature: "Shaft stress + critical speed"
    competitor:
      status: no
      note: "No native shaft design calculator; relies on Simulation FEA"
      source: "https://help.solidworks.com/2021/english/SolidWorks/cworks/c_Fatigue_Analysis.htm"
    kerf:
      status: partial
      note: "Closed-form shaft stress + critical speed backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/shaft"

  - domain: D3
    feature: "Weldments structural framework"
    competitor:
      status: yes
      note: "Structural member profiles, weldment cut lists, gussets"
      source: "https://help.solidworks.com/2023/english/SolidWorks/sldworks/c_profiles_cut_lists.htm"
    kerf:
      status: partial
      note: "Weldment profiles + cut-list engine; no full workspace"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/weldment_profiles.py"

  # ── D4 Thermal / fluid / HVAC ─────────────────────────────────────────────
  - domain: D4
    feature: "CFD (internal/external flow)"
    competitor:
      status: paid
      note: "SOLIDWORKS Flow Simulation — separately purchased add-in"
      source: "https://help.solidworks.com/2023/english/SolidWorks/floxpress/c_flow_simulation_overview.htm"
    kerf:
      status: partial
      note: "Real OpenFOAM bridge backend (needs install); no UI"
      evidence: "packages/kerf-fem/src/kerf_fem/cfd_navier_stokes.py"

  - domain: D4
    feature: "HVAC duct sizing (SMACNA)"
    competitor:
      status: no
      note: "No SMACNA duct sizing in SOLIDWORKS base product"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "SMACNA duct sizing + flat-pattern backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/hvac/ducts.py"

  - domain: D4
    feature: "Heat exchanger (LMTD/ε-NTU)"
    competitor:
      status: no
      note: "No thermal calc tools in base; Flow Simulation is CFD only"
      source: "https://help.solidworks.com/2025/English/SolidWorks/floxpress/r_what_do_flow_simulation.htm"
    kerf:
      status: partial
      note: "Full TEMA shell-tube with Bell-Delaware + 5 correction factors backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/heatxfer/shell_tube_bell.py"

  # ── D5 Aero / marine / space ──────────────────────────────────────────────
  - domain: D5
    feature: "Airfoil / wing aerodynamics (VLM)"
    competitor:
      status: no
      note: "No aerodynamic analysis tools in SOLIDWORKS; Flow Simulation is CFD"
      source: "https://help.solidworks.com/2025/English/SolidWorks/floxpress/r_what_do_flow_simulation.htm"
    kerf:
      status: yes
      note: "3D wing VLM + strip viscous CD0 + PG/KT compressibility; wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/aero/flow.py"

  - domain: D5
    feature: "Orbital mechanics (Kepler/Hohmann/Lambert)"
    competitor:
      status: no
      note: "No orbital mechanics tools in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: yes
      note: "Kepler + J2/J3 + Hohmann + Lambert (multi-rev) wired"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/aero/flow.py"

  # ── D6 Electronics / EDA / silicon ───────────────────────────────────────
  - domain: D6
    feature: "Schematic capture + PCB layout"
    competitor:
      status: paid
      note: "SOLIDWORKS PCB (Altium-derived add-in, separate purchase)"
      source: "https://help.solidworks.com/2022/english/Installation/install_guide/t_install_pcb_connector.htm"
    kerf:
      status: yes
      note: "Hierarchical schematic + PCB layout viewer wired in-browser"
      evidence: "packages/kerf-electronics/src/kerf_electronics/drc.py"

  - domain: D6
    feature: "Signal integrity (Z0/crosstalk/eye/IBIS)"
    competitor:
      status: no
      note: "No SI analysis in SOLIDWORKS; external tools required"
      source: "https://help.solidworks.com/2022/english/Installation/install_guide/t_install_pcb_connector.htm"
    kerf:
      status: partial
      note: "IBIS 5.1 + Bergeron channel + PRBS eye backend"
      evidence: "packages/kerf-electronics/src/kerf_electronics/eye"

  - domain: D6
    feature: "EMC (radiated/shielding/limits)"
    competitor:
      status: no
      note: "No EMC analysis in SOLIDWORKS; external tools required"
      source: "https://help.solidworks.com/2022/english/Installation/install_guide/t_install_pcb_connector.htm"
    kerf:
      status: partial
      note: "Closed-form radiated/shielding/limits backend; no full-wave"
      evidence: "packages/kerf-electronics/src/kerf_electronics/emc"

  - domain: D6
    feature: "Wiring / harness routing"
    competitor:
      status: paid
      note: "SOLIDWORKS Electrical 3D — separate add-in/licence"
      source: "https://help.solidworks.com/2024/English/swelec/r_swelec_route_harness.htm"
    kerf:
      status: yes
      note: "WiringView wired; WireViz + 3D router"
      evidence: "packages/kerf-wiring"

  # ── D7 Manufacturing / CAM ────────────────────────────────────────────────
  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: yes
      note: "SOLIDWORKS CAM Standard included with subscription service"
      source: "https://www.solidworks.com/product/solidworks-cam"
    kerf:
      status: yes
      note: "CAMView wired; profile/contour/pocket/face ops"
      evidence: "packages/kerf-cam/src/kerf_cam/worker.py"

  - domain: D7
    feature: "Multi-axis CAM (5-axis)"
    competitor:
      status: paid
      note: "SOLIDWORKS CAM Professional — separately purchased"
      source: "https://help.solidworks.com/2025/English/WhatsNew/c_wn_cam.htm"
    kerf:
      status: partial
      note: "5-axis 3+2 engine solid; no UI"
      evidence: "packages/kerf-cam/src/kerf_cam/five_axis/constant_tilt.py"

  - domain: D7
    feature: "Feeds & speeds + tool-life (Taylor/Gilbert)"
    competitor:
      status: partial
      note: "Basic feeds & speeds in SOLIDWORKS CAM; no Taylor/Gilbert model"
      source: "https://help.solidworks.com/2026/english/WhatsNew/c_wn_cam.htm"
    kerf:
      status: partial
      note: "Taylor extended + Gilbert economic speed backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/cuttingtool"

  - domain: D7
    feature: "Nesting (2D part layout)"
    competitor:
      status: no
      note: "No nesting in SOLIDWORKS base; third-party add-ins required"
      source: "https://www.solidworks.com/product/solidworks-cam"
    kerf:
      status: partial
      note: "Skyline + true-shape NFP + Minkowski-sum backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/nesting/nfp.py"

  - domain: D7
    feature: "Moldflow / injection fill simulation"
    competitor:
      status: no
      note: "No mold-fill simulation in SOLIDWORKS; separate Moldflow product"
      source: "https://www.solidworks.com/product/solidworks-cam"
    kerf:
      status: partial
      note: "Hele-Shaw front tracking + weld-line + air-trap backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/forming"

  - domain: D7
    feature: "FDM slicing"
    competitor:
      status: no
      note: "No slicer in SOLIDWORKS; exports STL to third-party slicers"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: yes
      note: "Cura integration wired (PrintSliceView)"
      evidence: "packages/kerf-slicing"

  # ── D8 Civil / infrastructure / geo ──────────────────────────────────────
  - domain: D8
    feature: "Road alignment (horizontal/vertical/clothoid)"
    competitor:
      status: no
      note: "No civil alignment tools in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "H+V alignment + clothoid + SSD backend; no plan export"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/civil/alignment.py"

  - domain: D8
    feature: "Geotech (bearing/settlement/slope/liquefaction)"
    competitor:
      status: no
      note: "No geotechnical analysis tools in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Seed-Idriss CSR + SPT/CPT CRR + Tokimatsu backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/geotech/liquefaction.py"

  # ── D9 Dynamics / motion / controls ──────────────────────────────────────
  - domain: D9
    feature: "Planar MBD (Lagrange/DAE)"
    competitor:
      status: paid
      note: "Motion Analysis requires SOLIDWORKS Simulation Premium add-in"
      source: "https://help.solidworks.com/2025/english/SolidWorks/motionstudies/t_detecting_interference_motion.htm"
    kerf:
      status: partial
      note: "Planar MBD Lagrange/DAE backend; not wired to assembly UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/dynamics/rigidbody.py"

  - domain: D9
    feature: "Controls — classical (Routh/Bode/PID)"
    competitor:
      status: no
      note: "No controls analysis tools in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Routh/Bode/RL/PID tune + state-space/LQR/Kalman backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/controls/statespace.py"

  - domain: D9
    feature: "Vibration (SDOF/n-DOF modal/FRF)"
    competitor:
      status: paid
      note: "Frequency analysis in SOLIDWORKS Simulation Standard/Professional"
      source: "https://help.solidworks.com/2026/english/simtutorialonline/c_simconn_fatigue.htm"
    kerf:
      status: partial
      note: "Full n-DOF eigen + FRF matrix backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/vibration/mdof.py"

  # ── D10 Electrical / energy / PLC / firmware ──────────────────────────────
  - domain: D10
    feature: "PLC IEC 61131-3 (ST/Ladder/FB)"
    competitor:
      status: no
      note: "No PLC programming in SOLIDWORKS; separate CODESYS ecosystem"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: yes
      note: "ST editor + live Ladder power-flow sim wired"
      evidence: "packages/kerf-plc/src/kerf_plc"

  - domain: D10
    feature: "Solar PV (system + partial shading)"
    competitor:
      status: no
      note: "No solar PV analysis in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Single-diode + bypass-diode IV + MPPT + mismatch backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/solarpv/shading.py"

  - domain: D10
    feature: "AC load-flow (Newton-Raphson)"
    competitor:
      status: no
      note: "No electrical power analysis in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Full polar-form NR load-flow backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/elecpower/loadflow.py"

  # ── D11 Tolerancing / metrology / QA ─────────────────────────────────────
  - domain: D11
    feature: "GD&T data model (ASME Y14.5)"
    competitor:
      status: yes
      note: "DimXpert per ASME Y14.41; geometric tolerancing tool"
      source: "https://help.solidworks.com/2022/English/WhatsNew/c_wn2022_mbd_dimxpert_geometric_tolerancing.htm"
    kerf:
      status: partial
      note: "Data model + auto-propose; no MBD/PMI placement UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/gdt/datums.py"

  - domain: D11
    feature: "Tolerance stackup — 1D (WC/RSS)"
    competitor:
      status: paid
      note: "TolAnalyst (WC + RSS) in SOLIDWORKS Premium"
      source: "https://help.solidworks.com/2025/english/SolidWorks/tolanalyst/c_TolAnalyst_Overview.htm"
    kerf:
      status: partial
      note: "WC/RSS/Monte-Carlo 1D backend; Monte-Carlo LCG bug"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolstack/stack.py"

  - domain: D11
    feature: "Tolerance stackup — 3D vector loop"
    competitor:
      status: paid
      note: "TolAnalyst 3D assembly stack in SOLIDWORKS Premium"
      source: "https://help.solidworks.com/2024/English/SolidWorks/tolanalyst/c_TolAnalyst_Overview.htm"
    kerf:
      status: partial
      note: "6-DOF vector loop + sensitivity Jacobian backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolstack/tol3d.py"

  - domain: D11
    feature: "Limits & fits (ISO 286)"
    competitor:
      status: yes
      note: "ISO 286 fit tolerances in dimension property manager"
      source: "https://help.solidworks.com/2021/english/SolidWorks/sldworks/c_fit_tolerances.htm"
    kerf:
      status: partial
      note: "ISO 286 limits & fits backend; no UI"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/tolfits/fits.py"

  - domain: D11
    feature: "SPC control charts (Shewhart/CUSUM/EWMA)"
    competitor:
      status: no
      note: "No SPC charts in SOLIDWORKS; external QA tools required"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Shewhart/CUSUM/EWMA + Nelson/WECO rules backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/spc/charts.py"

  # ── D12 Optics / acoustics ────────────────────────────────────────────────
  - domain: D12
    feature: "Paraxial ray tracing / Gaussian beam"
    competitor:
      status: no
      note: "No optics analysis in SOLIDWORKS; external Zemax/CODE V required"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "ABCD + Seidel + thick lens + Gaussian beam + M² backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/optics/lens.py"

  - domain: D12
    feature: "Acoustics (ISO 9613 / RT60 / mass-law TL)"
    competitor:
      status: no
      note: "No acoustics analysis in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "ISO 9613 + RT60 + mass-law TL + image-source IR backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/acoustics/sound.py"

  # ── D13 Verticals ─────────────────────────────────────────────────────────
  - domain: D13
    feature: "Jewelry design tooling"
    competitor:
      status: no
      note: "No jewelry-specific tooling in SOLIDWORKS"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: yes
      note: "41-module suite — ring/gem/setting/chain/casting/cost"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/jewelry"

  - domain: D13
    feature: "BIM / IFC authoring"
    competitor:
      status: no
      note: "No native BIM/IFC authoring; 3DExperience has limited AEC overlay"
      source: "https://www.solidworks.com/domain/data-management-collaboration"
    kerf:
      status: yes
      note: "Revit-comparable engine + IFC4 export wired via /compile-ifc"
      evidence: "packages/kerf-bim/src/kerf_bim"

  # ── D14 Cost / materials / LCA ────────────────────────────────────────────
  - domain: D14
    feature: "Material selection (Ashby / multi-objective)"
    competitor:
      status: no
      note: "Basic material properties only; no Ashby-style selection"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "200 materials + Pareto frontier + weighted-score backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/db.py"

  - domain: D14
    feature: "Should-cost / DFM estimation"
    competitor:
      status: no
      note: "No should-cost engine in SOLIDWORKS; third-party aPriori required"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "6-process Boothroyd-Dewhurst should-cost backend"
      evidence: "packages/kerf-cad-core/src/kerf_cad_core/costing/estimate.py"

  - domain: D14
    feature: "LCA (ISO 14040/44 full 4 phases)"
    competitor:
      status: no
      note: "No LCA tools in SOLIDWORKS; SimaPro/GaBi required externally"
      source: "https://help.solidworks.com/2024/english/SolidWorks/sldworks/c_features_top.htm"
    kerf:
      status: partial
      note: "Full 4-phase LCA + multi-impact + uncertainty backend"
      evidence: "packages/kerf-lca/src/kerf_lca"

  - domain: D14
    feature: "Scripting / automation API"
    competitor:
      status: yes
      note: "SOLIDWORKS API: VBA / VB.NET / C# / C++ COM interface"
      source: "https://help.solidworks.com/2024/english/api/sldworksapiprogguide/Welcome.htm"
    kerf:
      status: yes
      note: "kerf-sdk on PyPI — HTTP/JSON-RPC; same interface as LLM"
      evidence: "packages/kerf-sdk"
---

# Kerf vs SOLIDWORKS

SOLIDWORKS (Dassault Systèmes) is the dominant professional mechanical CAD platform with 30+ years of refinement, millions of seats, and the Parasolid kernel under the hood. Standard licence ~US$4,000 perpetual + ~$1,500/yr maintenance; subscription "SOLIDWORKS Connected" ~$2,200/yr (as of May 2026). Windows-only native desktop; 3DExperience cloud overlay is a separate purchase. Kerf will not out-SOLIDWORKS SOLIDWORKS on assembly motion, FEM, or add-in breadth — that is an honest statement. Where Kerf differs is MIT open-core licensing, no Windows-only constraint, chat-native editing, no per-seat fee, and a multi-discipline workspace that unifies mechanical, electronics, and jewelry design without additional add-ins or subscriptions.

## Where SOLIDWORKS is strong

- **Parasolid kernel and modeling depth.** SOLIDWORKS runs on the Parasolid B-rep kernel — the same engine used by Siemens NX and Solid Edge. Decades of production hardening across millions of real-world files give it a reliability track record that newer kernels have not yet accumulated.
- **Full assembly and motion simulation.** A complete mate system (coincident, concentric, gear, cam, screw, slot), interference detection, motion analysis with contacts, and mass-property roll-up across large assemblies — mature and production-proven.
- **FEM and CFD via add-ins.** SOLIDWORKS Simulation (static, thermal, fatigue, drop-test) and Flow Simulation (CFD) are integrated add-ins that have been tuned by real engineering teams for years.
- **Weldments and structural framework.** Structural-member profiles, weldment cut lists, gussets, and end treatments give fabricators a workflow purpose-built for structural steel and tubing.
- **NURBS surfacing (Premium / SurfaceWorks).** Class-A surface modelling tools for consumer products and automotive styling are mature in SOLIDWORKS Premium.
- **Large assembly handling.** Lightweight component mode, SpeedPak, and large assembly performance settings are well-tested workflows for thousand-part assemblies.
- **Vast add-in and VAR ecosystem.** Thousands of third-party add-ins — CAM (CAMWorks, HSMWorks), PDM (SOLIDWORKS PDM), rendering (KeyShot), ERP connectors — and a global network of certified resellers.
- **Market standard and hiring pool.** SOLIDWORKS proficiency is a near-universal requirement on mechanical engineering job descriptions.

## Where Kerf differs

- **MIT open-core, no seat fee.** The full feature set is MIT-licensed and free to install locally. No $4,000 seat, no annual maintenance contract, no add-in stacking, no commercial-use restriction.
- **Chat-native workflow and BYO LLM.** Describe a feature, sketch constraint, or assembly change in plain English; the model edits the feature-tree source backed by live doc-search. Bring your own Anthropic or compatible API key with zero billing routed through Kerf.
- **CAM included in-box.** 3-axis CAM with tool DB and 5-axis 3+2 ship as part of the core product — no CAMWorks or HSMWorks add-in required.
- **Cross-platform, browser + local binary.** Runs in the browser (hosted SaaS) or as a single local binary on Windows, macOS, and Linux. No Parallels, no dedicated Windows box.
- **Full ECAD in one workspace — no add-in.** Hierarchical schematic, PCB layout, shove router, SPICE, IPC fab output, and the full pre-compliance simulation suite (SI, EMC, PDN, thermal) are built into the same workspace as the B-rep modeller, with no separate ECAD licence.
- **40-module jewelry domain.** Ring v4, gemstones v2 (30 cuts), settings v3/v4, gem-seat v2, chain v2, findings, casting export, full cost panel, and PBR gem/metal viewport materials — a professional jewelry vertical with no SOLIDWORKS counterpart we're aware of.
- **Cloud git built in.** Every project gets fine-grained file revision history (undo) plus deliberate cloud-git commits with GitHub sync — no PDM server setup, no extra subscription.
- **kerf-sdk Python scripting.** Automate B-rep, PCB, and jewelry workflows from a Python script on your own machine over HTTP/JSON-RPC.

## Honest gaps — where Kerf is behind today

- **Assembly motion study.** Kerf now matches SOLIDWORKS' joint type set (including gear, cam, pin-slot), but motion analysis, contact sets, and interference detection are not yet shipped in Kerf.
- **FEM multi-physics depth and CFD.** Kerf ships linear static, thermal, and nonlinear plasticity FEM, but SOLIDWORKS Simulation (fatigue, frequency, buckling) and Flow Simulation (CFD) are significantly more mature. CFD is not in Kerf.
- **NURBS surfacing depth.** SOLIDWORKS Premium's surfacing tools are significantly ahead of Kerf's NURBS Phase 4, which is early and scope-limited.
- **Weldments workspace.** SOLIDWORKS' structural member profiles, weldment cut lists, and gussets are a fabrication workflow Kerf does not replicate.
- **Large assembly tooling.** Lightweight components, SpeedPak, and large-assembly performance settings have no Kerf equivalent today.
- **SOLIDWORKS API depth.** The SOLIDWORKS COM API has 20+ years of depth covering every feature, mate, and drawing entity. Kerf's kerf-sdk is younger.
- **Add-in and VAR ecosystem.** Thousands of certified third-party add-ins and a global VAR network are irreplaceable near-term.

## Side by side

| Feature | SOLIDWORKS | Kerf |
|---|---|---|
| License | ⚠️ Proprietary perpetual + maintenance or subscription | ✅ MIT open-core |
| Cost | ⚠️ ~US$4,000 perpetual + ~$1,500/yr; or ~$2,200/yr Connected (May 2026) | ✅ Free local; pay-as-you-go hosted |
| Platform | ⚠️ Windows only | ✅ Browser + Win/macOS/Linux binary |
| Offline / self-host | ✅ Full offline (perpetual) | ✅ pip install 'kerf[server]' + kerf serve |
| Parametric B-rep | ✅ Parasolid feature tree | ✅ OCCT feature tree |
| Constraint sketcher | ✅ Full parametric sketcher | ✅ Sketcher v2 — all major constraints |
| Sheet metal | ✅ Full — flange, mitre, flat pattern | ✅ Flange + hem + jog + multi-flange + unfold + flat DXF |
| NURBS surfacing | ✅ SurfaceWorks-class (Premium) | ✅ blend/network/patch/match-srf + Class-A harness (younger kernel) |
| Assembly / mates | ✅ Full mate system — gear / cam / screw | ✅ Full joint system — rigid/revolute/slider/cam/gear/pin-slot |
| Motion study | ✅ Motion analysis, interference | ❌ Not yet |
| Large assembly mode | ✅ SpeedPak, lightweight components | ⚠️ LOD mesh swapping (configurable) |
| 2D drawings | ✅ Full drawing environment | ✅ Multi-sheet drawings |
| GD&T | ✅ ASME / ISO GD&T with DimXpert | ✅ ASME Y14.5 datum + tolerance framework |
| CNC CAM (3-axis) | ⚠️ Requires CAMWorks / HSMWorks add-in | ✅ 3-axis CAM + tool DB (in-box) |
| Multi-axis CAM | ⚠️ Add-in required (extra cost) | ✅ 5-axis CAM 3+2 (in-box) |
| FEM / structural | ✅ SW Simulation (add-in) | ⚠️ Linear static + thermal; not full parity |
| CFD | ✅ Flow Simulation (add-in) | ❌ Not yet |
| Electronics / PCB | ⚠️ SOLIDWORKS PCB (Altium-derived, add-in) | ✅ Full hierarchical schematic + PCB layout in-box |
| SI / EMC / PDN / thermal | ❌ No integrated equivalent we're aware of (as of May 2026) | ✅ si_eye_wizard + emc_wizard + pdn_wizard + thermal_board in-box |
| Jewelry tooling | ❌ None we're aware of (as of May 2026) | ✅ 40-module jewelry suite |
| Chat / LLM editing | ❌ No LLM editing shipped to our knowledge (as of May 2026) | ✅ Chat-native + BYO API key |
| Scripting / API | ✅ SOLIDWORKS API (COM/VBA/C#) | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| Multi-user cloud edit | ⚠️ 3DExperience (separate SaaS) | ✅ Cloud hosted + cloud-git sync |
| Open source | ❌ Proprietary | ✅ MIT — full codebase on GitHub |
