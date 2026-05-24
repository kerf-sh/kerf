---
slug: freecad
competitor: "FreeCAD"
category: cad-mechanical
left: kerf
right: freecad
hero_tagline: "Open-source parametric B-rep modeller — LGPL vs MIT, desktop vs cloud."
reviewed_at: 2026-05-19
order: 1
features:

  # D1 — Geometry & core CAD
  - name: Constraint sketcher (geo + dim)
    competitor:
      status: yes
      source: https://wiki.freecad.org/Sketcher_Workbench
      note: "Sketcher WB — mature solver, all standard constraints"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/sketch.py
      note: "PlaneGCS WASM; missing collinear, ellipse entity, G2"

  - name: Pad / pocket / revolve
    competitor:
      status: yes
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "PartDesign WB — Pad, Pocket, Revolution (core operations)"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/tests/test_revolve_to_body.py
      note: "OCCT, wired"

  - name: Fillet / chamfer (constant)
    competitor:
      status: yes
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "PartDesign Fillet and Chamfer tools"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/geom/history/feature.py
      note: "wired"

  - name: Sweep (1 & 2 rail)
    competitor:
      status: yes
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "PartDesign AdditivePipe / SubtractivePipe"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/surfacing.py
      note: "BRepOffsetAPI_MakePipeShell"

  - name: Loft
    competitor:
      status: yes
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "PartDesign AdditiveLoft / SubtractiveLoft"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/feature_loft.py
      note: "guide-rail overload wired (ThruSections.AddWire); ruled/closed/symmetric"

  - name: Sheet metal
    competitor:
      status: partial
      source: https://wiki.freecad.org/SheetMetal_Workbench/en
      note: "SheetMetal addon (community) — bend/unfold/flat-pattern/K-factor"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/construction_verbs_tools.py
      note: "flange + hem + jog + multi-flange + unfold + flat DXF (K-factor)"

  - name: Assemblies — mates
    competitor:
      status: yes
      source: https://blog.freecad.org/2024/09/30/tutorial-getting-started-with-the-assembly-workbench/
      note: "Built-in Assembly WB (FreeCAD 1.0) — Ondsel solver"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/assembly/__init__.py
      note: "rigid/revolute/slider/cam/gear/pin-slot + BOM panel"

  - name: Assembly interference (clash)
    competitor:
      status: yes
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "Part Check Geometry + Boolean intersection"
    kerf:
      status: partial
      evidence: packages/kerf-cad-core/src/kerf_cad_core/clash/detect.py
      note: "backend OBB-SAT + BVH; no UI panel"

  - name: 2D drawings (views/dims/sections)
    competitor:
      status: yes
      source: https://wiki.freecad.org/TechDraw_Workbench
      note: "TechDraw WB — HLR projections, sections, dimensions"
    kerf:
      status: partial
      evidence: packages/kerf-cad-core/src/kerf_cad_core/geom/history/feature_io.py
      note: "live HLR projection + auto-dim; no GD&T-placement UI"

  - name: NURBS surfacing (blend/network/patch)
    competitor:
      status: partial
      source: https://wiki.freecad.org/Workbenches
      note: "Surface WB (built-in, limited) — no class-A NURBS"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/geom/network_srf.py
      note: "blend_srf, network_srf (Gordon), patch_srf_fit, match_srf, G3 blends wired"

  - name: Configurations / family variants
    competitor:
      status: partial
      source: https://wiki.freecad.org/Spreadsheet_Workbench
      note: "Spreadsheet-driven parameters; no formal config table"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/assembly/__init__.py
      note: "engine + ConfigurationsPanel.jsx wired"

  - name: Direct edit (push-pull)
    competitor:
      status: partial
      source: https://wiki.freecad.org/PartDesign_Workbench
      note: "Part WB — limited direct face editing"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/geom/direct_edit.py
      note: "push_pull (planar + curved), move_face, delete_face wired as ops"

  # D2 — Structural / FEA
  - name: FE — solid (tet/hex) solver
    competitor:
      status: yes
      source: https://wiki.freecad.org/FEM_Module/en
      note: "FEM WB — CalculiX / Elmer / Z88 / Mystran built-in"
    kerf:
      status: yes
      evidence: packages/kerf-fem/src/kerf_fem/calculix_bridge.py
      note: "CalculiX/Mystran/Z88 bridge (needs binary; backend)"

  - name: FE — plate / shell (native)
    competitor:
      status: yes
      source: https://wiki.freecad.org/FEM_Module/en
      note: "CalculiX shell elements via FEM WB"
    kerf:
      status: yes
      evidence: packages/kerf-fem/src/kerf_fem/linear_static.py
      note: "MITC4 Bathe-Dvorkin + modal; 1.29% error (backend)"

  - name: Modal / buckling / nonlinear FEA
    competitor:
      status: yes
      source: https://blog.freecad.org/2024/09/28/major-fem-workbench-improvements-for-freecad-1-0/
      note: "FEM WB 1.0 — CalculiX modal + nonlinear analysis"
    kerf:
      status: yes
      evidence: packages/kerf-fem/src/kerf_fem/modal.py
      note: "consistent-mass modal, Riks, J2 plasticity (backend)"

  - name: AISC / ACI / NDS per-code design checks
    competitor:
      status: no
      source: https://wiki.freecad.org/FEM_Module/en
      note: "FEM WB is FEA only; no per-code design checks"
    kerf:
      status: yes
      evidence: packages/kerf-structural/src/kerf_structural/steel_beam.py
      note: "AISC 360-22, ACI 318-19, NDS 2018 (backend)"

  - name: Eurocode design (EC2/EC3/EC5/EC8)
    competitor:
      status: no
      source: https://wiki.freecad.org/FEM_Module/en
      note: "no code-check calculators built in"
    kerf:
      status: yes
      evidence: packages/kerf-structural/src/kerf_structural/tools.py
      note: "full EC2/3/5/8 coverage (backend)"

  # D3 — Machine elements
  - name: Gear rating (AGMA / ISO 6336)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "GearWB generates geometry only; no AGMA/ISO rating calc"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/bearings/__init__.py
      note: "AGMA 2001-D04 + ISO 6336 Method B (backend)"

  - name: Bearings (ISO 281 / ISO/TS 16281)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no bearing life calculation in core"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/bearings/__init__.py
      note: "ISO 281 L10 + aISO modified life (backend)"

  - name: Fasteners — VDI 2230 bolt calc
    competitor:
      status: partial
      source: https://wiki.freecad.org/Fasteners_Workbench
      note: "Fasteners addon generates geometry; no VDI 2230 calc"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/assembly/__init__.py
      note: "VDI 2230 preload + fatigue analysis (backend)"

  - name: Springs / belt-chain / shaft design
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no built-in machine element calculators"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/beltchain/__init__.py
      note: "Shigley-grade springs/belt/chain/shaft (backend)"

  # D4 — Thermal / fluid / HVAC
  - name: CFD (OpenFOAM bridge)
    competitor:
      status: partial
      source: https://github.com/jaheyns/CfdOF
      note: "CfdOF addon — OpenFOAM; requires addon install"
    kerf:
      status: yes
      evidence: packages/kerf-fem/src/kerf_fem/cfd_navier_stokes.py
      note: "real OpenFOAM bridge (backend; needs install)"

  - name: Heat exchanger (LMTD / ε-NTU / Bell-Delaware)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no thermal calc tools in core"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/thermocycle/cycles.py
      note: "LMTD + ε-NTU + Bell-Delaware + TEMA (backend)"

  - name: HVAC duct sizing (SMACNA)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no HVAC calculators in core"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/buildingenergy/__init__.py
      note: "SMACNA duct sizing + flat-pattern (backend)"

  - name: Steam / fluid properties (IAPWS-IF97)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no fluid property library"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/thermocycle/cycles.py
      note: "IAPWS-IF97 Regions 1/2/4; refrigerant partial"

  # D5 — Aero / marine / space
  - name: Airfoil / wing VLM aero analysis
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no built-in aero analysis; geometry drafting only"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/aero/__init__.py
      note: "NACA 4/5 + panel + VLM viscous + compressibility (wired)"

  - name: Orbital mechanics (Kepler / Lambert)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no orbital mechanics tools"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/aero/__init__.py
      note: "Kepler, J2/J3, Hohmann, multi-rev Lambert (wired)"

  - name: Naval hydrostatics + GZ stability (IMO)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no marine engineering tools"
    kerf:
      status: yes
      evidence: packages/kerf-marine/src/kerf_marine/hydrostatics.py
      note: "hydrostatics + IMO GZ + seakeeping RAOs (wired)"

  # D6 — Electronics / EDA / silicon
  - name: Schematic capture / PCB layout viewer
    competitor:
      status: partial
      source: https://github.com/marmni/FreeCAD-PCB
      note: "PCB addon (community) — imports KiCad board into MCAD"
    kerf:
      status: yes
      evidence: packages/kerf-electronics/src/kerf_electronics/kicad_io.py
      note: "KiCad round-trip viewer + ERC wired (read-only)"

  - name: SPICE simulation
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no SPICE engine in core or official addons"
    kerf:
      status: yes
      evidence: packages/kerf-electronics/src/kerf_electronics/routes_spice.py
      note: "real ngspice wired"

  - name: Signal integrity / EMC / PDN
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no SI/EMC/PDN analysis tools"
    kerf:
      status: yes
      evidence: packages/kerf-electronics/src/kerf_electronics/si_eye_wizard.py
      note: "IBIS + Bergeron + PRBS eye + PDN AC impedance (backend)"

  - name: DRC / ERC
    competitor:
      status: partial
      source: https://github.com/marmni/FreeCAD-PCB
      note: "PCB addon provides basic checks; not full KiCad DRC"
    kerf:
      status: yes
      evidence: packages/kerf-electronics/src/kerf_electronics/drc.py
      note: "DRC overlay wired"

  - name: Silicon synthesis / P&R (Yosys / OpenLane)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no silicon digital/analog EDA tooling"
    kerf:
      status: yes
      evidence: packages/kerf-electronics/src/kerf_electronics/sim_corner.py
      note: "Yosys/STA/GDS/OpenLane bridge (backend; zero UI)"

  # D7 — Manufacturing / CAM
  - name: 3-axis CAM (profile/pocket/face/drill)
    competitor:
      status: yes
      source: https://wiki.freecad.org/CAM_Workbench
      note: "CAM WB (built-in) — profile/pocket/drill/face + simulator"
    kerf:
      status: yes
      evidence: packages/kerf-cam/src/kerf_cam/plugin.py
      note: "CAMView wired; profile/contour/pocket/face"

  - name: 5-axis CAM
    competitor:
      status: no
      source: https://wiki.freecad.org/Path_FAQ/en
      note: "CAM WB supports up to 3-axis; no official 5-axis"
    kerf:
      status: partial
      evidence: packages/kerf-cam/src/kerf_cam/five_axis/__init__.py
      note: "5-axis engine solid; no UI"

  - name: Turning cycles (lathe)
    competitor:
      status: partial
      source: https://wiki.freecad.org/Path_FAQ/en
      note: "TurningAddon (community via LibLathe); not built-in"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/turning/__init__.py
      note: "G71/G70/threading turning cycles (backend)"

  - name: G-code post-processor
    competitor:
      status: yes
      source: https://wiki.freecad.org/CAM_Post
      note: "CAM WB — Fanuc / LinuxCNC / GRBL + custom postprocessors"
    kerf:
      status: yes
      evidence: packages/kerf-cam/src/kerf_cam/posts/__init__.py
      note: "Fanuc/GRBL/LinuxCNC/Mach3; no G41/42 cutter-comp"

  - name: Moldflow / fill simulation
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no injection moulding simulation"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/casting/__init__.py
      note: "Hele-Shaw front + weld-line + air-trap (backend)"

  - name: Nesting (sheet / panel)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no true-shape nesting"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/dfm/checks.py
      note: "Minkowski-sum NFP + skyline nesting (backend)"

  - name: FDM slicing (Cura)
    competitor:
      status: partial
      source: https://wiki.freecad.org/Workbenches
      note: "exports STL; no built-in slicer (external Cura/PrusaSlicer)"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/additive/__init__.py
      note: "PrintSliceView wired (Cura bridge)"

  # D8 — Civil / infrastructure / geo
  - name: Horizontal + vertical alignment (clothoid)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no civil road/rail alignment tools"
    kerf:
      status: yes
      evidence: packages/kerf-civil/src/kerf_civil/horizontal_alignment.py
      note: "clothoid + SSD + superelevation (backend)"

  - name: Geodesy / projections (UTM / Vincenty)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no geodetic projection library"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/geodesy/geo.py
      note: "Vincenty, TM, UTM, LCC (backend)"

  - name: Geotech (bearing / settlement / liquefaction)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no geotechnical calculators"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/civil/__init__.py
      note: "Seed-Idriss CSR + SPT/CPT CRR (backend)"

  # D9 — Dynamics / motion / controls
  - name: Assembly motion / kinematics simulation
    competitor:
      status: partial
      source: https://github.com/FreeCAD/FreeCAD/discussions/22241
      note: "Assembly WB 1.1 adds basic simulation; MBDyn addon available"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/kinematics/linkage.py
      note: "planar MBD + 4-bar/slider-crank/cam (backend)"

  - name: Robotics FK / IK (6-DOF)
    competitor:
      status: partial
      source: https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Robot/RobotExample.py
      note: "Robot WB (experimental) — FK; IK limited"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/kinematics/tools.py
      note: "planar + 6-DOF DLS Jacobian IK (backend)"

  - name: Controls (PID / state-space / LQR / Kalman)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no control system toolbox"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/controls/__init__.py
      note: "Routh/Bode/PID + LQR + Kalman + c2d ZOH (backend)"

  # D10 — Electrical / energy / PLC / firmware
  - name: PLC (IEC 61131-3 ST / Ladder)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no PLC programming environment"
    kerf:
      status: yes
      evidence: packages/kerf-plc/src/kerf_plc/__init__.py
      note: "ST editor + live Ladder power-flow sim wired"

  - name: Firmware build / upload / monitor
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no embedded firmware tooling"
    kerf:
      status: yes
      evidence: packages/kerf-firmware/src/kerf_firmware/build.py
      note: "FirmwareActions + debug panel wired"

  - name: Solar PV (system + partial shading + MPPT)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no energy / solar simulation tools"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/solarpv/__init__.py
      note: "single-diode + bypass-diode IV + global MPPT (backend)"

  - name: Wiring / harness (WireViz + 3D router)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "IDF MCAD bridge only; no native harness routing"
    kerf:
      status: yes
      evidence: packages/kerf-wiring/src/kerf_wiring/wireviz_runner.py
      note: "WiringView + 3D harness router wired"

  # D11 — Tolerancing / metrology / QA
  - name: GD&T annotations (drawings)
    competitor:
      status: partial
      source: https://wiki.freecad.org/TechDraw_Workbench
      note: "TechDraw — GD&T symbols, surface finish, ISO/ASME style"
    kerf:
      status: partial
      evidence: packages/kerf-gdnt/src/kerf_gdnt/__init__.py
      note: "ASME Y14.5 data model + auto-propose; no UI placement"

  - name: Tolerance stackup (1D WC/RSS/MC + 3D)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no tolerance stackup calculator"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/tolstack/__init__.py
      note: "WC/RSS/MC + 3D vector loop + Jacobian (backend)"

  - name: Process capability (Cpk / SPC charts)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no SPC / Cpk tooling"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/analysis.py
      note: "Cpk/Ppk + Shewhart/CUSUM/EWMA SPC (backend)"

  # D12 — Optics / acoustics
  - name: Optical ray tracing (paraxial + non-sequential)
    competitor:
      status: partial
      source: https://github.com/zaphB/freecad.optics_design_workbench
      note: "Optics Design addon (community) — Monte-Carlo ray tracing"
    kerf:
      status: yes
      evidence: packages/kerf-optics/src/kerf_optics/ray_transfer.py
      note: "paraxial ABCD + Seidel + NSC + Gaussian beam (backend)"

  - name: Acoustics (ISO 9613 / RT60 / mass-law TL)
    competitor:
      status: partial
      source: https://github.com/rgon/freecad-acoustics
      note: "freecad-acoustics WIP addon (community); loudspeaker focus"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/acoustics/__init__.py
      note: "ISO 9613 + RT60 + weighting + TL + wave SEA (backend)"

  # D13 — Verticals
  - name: Jewelry design (gems / settings / rings)
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no native jewelry tooling whatsoever"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/jewelry/gem_seat.py
      note: "41 modules — gemstones v2, settings v3/v4, ring v4"

  - name: BIM / architecture (walls / slabs / IFC)
    competitor:
      status: yes
      source: https://wiki.freecad.org/Arch_IFC
      note: "BIM WB (merged Arch) — full IFC import/export, walls/slabs"
    kerf:
      status: partial
      evidence: packages/kerf-cad-core/src/kerf_cad_core/arch/primitives.py
      note: "IFC Tier 2 import + engine; IFC export in progress"

  - name: Textiles / apparel
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no textiles or drape simulation"
    kerf:
      status: partial
      evidence: packages/kerf-textiles/src/kerf_textiles/mass_spring.py
      note: "weave/knit/drape/cut-room (backend); no 3D avatar"

  # D14 — Cost / materials / LCA
  - name: Material selection (Ashby / multi-objective)
    competitor:
      status: partial
      source: https://wiki.freecad.org/Material_Workbench
      note: "Material WB — property lookup; no Ashby charts"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/matsel/db.py
      note: "200 materials + Pareto frontier + weighted-score (backend)"

  - name: Should-cost / Boothroyd-Dewhurst estimation
    competitor:
      status: no
      source: https://wiki.freecad.org/Workbenches
      note: "no cost estimation engine"
    kerf:
      status: yes
      evidence: packages/kerf-cad-core/src/kerf_cad_core/costing/__init__.py
      note: "Boothroyd-Dewhurst 6 processes + geometry-driven RFQ"

  - name: LCA (ISO 14040/44 full 4 phases)
    competitor:
      status: no
      source: https://forum.freecad.org/viewtopic.php?style=4&p=454996
      note: "no built-in LCA; forum only points to external openLCA"
    kerf:
      status: yes
      evidence: packages/kerf-lca/src/kerf_lca/report.py
      note: "ISO 14040/44 4 phases + multi-impact categories (backend)"
---

# Kerf vs FreeCAD

FreeCAD reached 1.0 in November 2024 after ~20 years of development: a genuinely mature, LGPL, desktop parametric CAD package with a built-in Assembly workbench, FEM (CalculiX/Elmer/Z88/Mystran), a rewritten CAM ecosystem, and hundreds of community workbenches. Kerf is far younger and narrower in ecosystem — but adds a chat-native workflow, an MIT open-core licence, a hosted option, and integrated electronics and jewelry in one workspace. Below is an honest look at both.

## Where FreeCAD is strong

- **Mature, proven parametric modelling.** The Part Design and Sketcher workbenches have been refined for roughly two decades. FreeCAD 1.0 largely resolved the long-standing topological-naming problem for Sketcher and Part Design.
- **Built-in Assembly workbench.** FreeCAD 1.0 ships a first-party Assembly workbench with a modern constraint solver — no longer a third-party add-on. Kerf's assembly mates are newer and less battle-tested.
- **Real FEM simulation.** The FEM workbench drives CalculiX, Elmer, Z88, and Mystran for structural (static, modal, buckling) and thermal analysis — a depth Kerf has not yet matched.
- **Hundreds of community workbenches.** SheetMetal, Path/CAM, Arch/BIM, FEM, Render, and many more. If a specialised workflow exists, there is usually a workbench for it.
- **Deep, in-process Python API.** FreeCAD's scripting surface covers virtually every internal object type, with an enormous body of macros and documentation.
- **Completely free, fully offline.** No subscription, no account, no cloud dependency — Windows, macOS, and Linux desktop.
- **Broad, certified interoperability.** STEP, IGES, DXF, IFC, STL, OBJ, and BREP import/export are well-exercised across a huge user base.

## Where Kerf differs

- **Chat-native workflow.** Every design turn can be driven by a chat message; the model edits the underlying source (feature tree / JSCAD) directly, backed by live doc-search so it does not invent API surface.
- **Electronics + mechanical in one workspace.** Kerf includes a full EDA stack — schematic, routing, DRC, Gerber / IPC-2581 fab pack — alongside B-rep CAD. FreeCAD offers only an IDF MCAD bridge to an external EDA tool.
- **MIT open-core, with a hosted option.** The core is permissively MIT-licensed (FreeCAD is copyleft LGPL). A hosted SaaS version runs in the browser; a single binary installs locally via brew or curl.
- **kerf-sdk on PyPI.** Python scripting over HTTP/JSON-RPC from your own machine — the same interface the LLM uses internally, so scripts are first-class and out-of-process rather than an embedded console.
- **Jewelry built in.** Gemstones v2 (30 cuts), settings v3/v4, gem-seat v2, ring v4, chain v2, findings, casting export, and a 31-template library — a domain FreeCAD has no native tooling for, as far as we're aware (as of May 2026).
- **GD&T to ASME Y14.5.** A full datum and tolerance framework, where FreeCAD's TechDraw offers comparatively basic annotation.
- **Every project is a real git repo.** Projects are cloneable git repositories with large-file handling, near-free forks, optional GitHub or GitLab mirror, and CLI sync.
- **Full mechanical joint system.** Rigid, revolute, slider, cam, gear, and pin-slot joints are all available, bringing Kerf's assembly depth much closer to FreeCAD's built-in Assembly workbench.

## Honest gaps — where Kerf is behind today

- **FEM depth is narrower.** Kerf ships linear static, thermal, and nonlinear plasticity FEM, but FreeCAD's workbench (CalculiX/Elmer/Z88/Mystran) covers more solver types, boundary conditions, and multi-physics coupling. CFD (OpenFOAM via CfdOF) is not in Kerf at all.
- **Far smaller ecosystem.** FreeCAD has hundreds of community workbenches and ~20 years of accumulated tooling. Kerf's plugin API is early-stage.
- **Less community and documentation.** FreeCAD has a decade-old forum, wiki, and YouTube ecosystem. Kerf is young and the documentation is still growing.
- **No IFC export.** FreeCAD exports IFC. Kerf imports IFC at Tier 2 but does not yet export IFC.

## Side by side

| Feature | FreeCAD | Kerf |
|---|---|---|
| License | ✅ LGPL v2.1+ (free, copyleft) | ✅ MIT open-core (permissive) |
| Cost | ✅ Free, no subscription | ✅ Free local binary; pay-as-you-go hosted |
| Platform | ✅ Win / macOS / Linux desktop | ✅ Browser + single-binary local |
| Hosted / cloud | ❌ Desktop only | ✅ Hosted SaaS + local install |
| Maturity | ✅ 1.0 in 2024, ~20 yr history | ⚠️ Early-stage, < 2 yr public |
| Parametric B-rep | ✅ Part Design WB (OCCT) | ✅ OCCT feature tree — pad/pocket/revolve/loft |
| Constraint sketcher | ✅ Sketcher WB (mature solver) | ✅ Sketcher v2 — all major constraints |
| Topological naming | ✅ Largely fixed in 1.0 | ✅ Persistent face names (Phase 4) |
| NURBS surfacing | ⚠️ Surface WB (limited) | ✅ blend/network/patch/match-srf + G3 blends (younger) |
| Sheet metal | ✅ SheetMetal WB (community) | ✅ Flange + hem + jog + multi-flange + unfold + flat DXF |
| Assembly / mates | ✅ Built-in Assembly WB (1.0, new solver) | ✅ Full joint system — rigid/revolute/slider/cam/gear/pin-slot |
| 2D technical drawings | ✅ TechDraw WB | ✅ Multi-sheet drawings |
| GD&T | ⚠️ TechDraw annotations (basic) | ✅ ASME Y14.5 datum + tolerance framework |
| CNC CAM | ✅ CAM/Path WB (rewritten in 1.1) | ✅ 3-axis CAM + tool DB; 5-axis 3+2 |
| Slicing / 3D print | ⚠️ Via external slicer | ✅ Slicing Tier 1 built in |
| FEM (structural / thermal) | ✅ FEM WB — CalculiX / Elmer / Z88 / Mystran | ⚠️ Linear static + thermal; not full parity |
| CFD | ⚠️ CfdOF add-on (OpenFOAM) | ❌ Not yet |
| Electronics / PCB | ⚠️ IDF MCAD bridge only | ✅ Full EDA — schematic, routing, DRC, Gerber/IPC-2581 |
| Jewelry | ❌ No native jewelry tooling | ✅ Gemstones v2, settings v3/v4, ring v4, chain v2 |
| Architecture / BIM | ✅ Arch + BIM WB, IFC import/export | ⚠️ IFC Tier 2 import; IFC export in progress |
| Python scripting | ✅ Deep in-process macro/console API | ✅ kerf-sdk on PyPI — HTTP/JSON-RPC |
| Chat / LLM editing | ❌ None | ✅ Chat-native — edits source per turn |
| Plugin ecosystem | ✅ Hundreds of community workbenches | ⚠️ Early — open-core + plugin API |
| Import formats | ✅ STEP/IGES/DXF/IFC/STL/OBJ/BREP | ✅ STEP/IGES/IFC/DXF/DWG/FreeCAD import |
