---
slug: calculix
competitor: CalculiX
category: cad-sim
left: kerf
right: calculix
hero_tagline: "CalculiX runs the FEM — Kerf wraps it so structural analysis is as easy as describing the load case."
reviewed_at: 2026-05-24
features:
  - domain: D2
    feature: "FE — solid (tet/hex)"
    competitor:
      status: yes
      note: "ccx solver; C3D4/C3D8/C3D10/C3D20 elements, linear + nonlinear"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "CalculiX bridge"
      evidence: "packages/kerf-fem/src/kerf_fem/calculix_bridge.py"

  - domain: D2
    feature: "Modal / buckling / nonlinear"
    competitor:
      status: yes
      note: "FREQUENCY, BUCKLE, *NLGEOM, Riks arc-length steps"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "consistent-mass modal, Riks, J2 plasticity"
      evidence: "packages/kerf-fem/src/kerf_fem/calculix_bridge.py"

  - domain: D2
    feature: "FE — plate / shell (native)"
    competitor:
      status: yes
      note: "S4, S4R, S8, S8R shell elements; *SHELL SECTION"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "MITC4 Bathe-Dvorkin native; shell also via CalculiX bridge"
      evidence: "packages/kerf-fem/src/kerf_fem/plate.py"

  - domain: D2
    feature: "FE — 1D beam / 2D truss (native)"
    competitor:
      status: yes
      note: "B31, B32, T3D2, T3D3; *BEAM SECTION"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "Hermite beam native; validated vs Roark"
      evidence: "packages/kerf-fem/src/kerf_fem/beam.py"

  - domain: D2
    feature: "AISC 360-22 steel (members)"
    competitor:
      status: no
      note: "solver only — no code-check post-processing"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "full Ch. E/F/H/I, 50-section catalog"
      evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py"

  - domain: D2
    feature: "ACI 318-19 concrete"
    competitor:
      status: no
      note: "solver only — no RC code-check"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "flexure/shear/PM/dev-length"
      evidence: "packages/kerf-structural/src/kerf_structural/concrete.py"

  - domain: D2
    feature: "Eurocode design (EC2/3/5/8)"
    competitor:
      status: no
      note: "solver only — no Eurocode post-processing"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "EC2 concrete + EC3 steel + EC5 timber + EC8 seismic"
      evidence: "packages/kerf-structural/src/kerf_structural/eurocode.py"

  - domain: D2
    feature: "ASCE 7-22 seismic"
    competitor:
      status: no
      note: "solver only — no seismic code-check"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "ELF + RSA (SRSS+CQC) + Newmark time-history"
      evidence: "packages/kerf-structural/src/kerf_structural/seismic/rsa.py"

  - domain: D2
    feature: "ASCE 7-22 wind (MWFRS+C&C)"
    competitor:
      status: no
      note: "solver only — no wind load generation"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "MWFRS + C&C per ASCE 7-22"
      evidence: "packages/kerf-structural/src/kerf_structural/wind.py"

  - domain: D2
    feature: "Fatigue (S-N, ε-N, rainflow)"
    competitor:
      status: partial
      note: "stress output only; no built-in S-N cycle counting or damage"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "S-N, ε-N, rainflow counting, Miner's rule"
      evidence: "packages/kerf-structural/src/kerf_structural/fatigue.py"

  - domain: D2
    feature: "ASME VIII pressure vessel"
    competitor:
      status: no
      note: "solver only — no ASME VIII code equations"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "ASME VIII Div 1 thickness + nozzle + wind/seismic"
      evidence: "packages/kerf-structural/src/kerf_structural/pressure_vessel.py"

  - domain: D2
    feature: "Frame stiffness assembly (2D/3D)"
    competitor:
      status: yes
      note: "full 3D beam-column FEM; *STEP STATIC with NLGEOM"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "2D+3D beam-column + ASCE 7 combos + story drift"
      evidence: "packages/kerf-structural/src/kerf_structural/frame.py"

  - domain: D2
    feature: "API 650 tank"
    competitor:
      status: no
      note: "solver only — no API 650 annular/shell design equations"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "API 650 incl. seismic annex E"
      evidence: "packages/kerf-structural/src/kerf_structural/api650.py"

  - domain: D2
    feature: "NDS 2018 timber"
    competitor:
      status: no
      note: "solver only — no NDS code-check"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "full NDS 2018 adjustment factors"
      evidence: "packages/kerf-structural/src/kerf_structural/timber.py"

  - domain: D2
    feature: "AISC steel connections"
    competitor:
      status: no
      note: "solver only — no connection design"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "bolts/welds/base-plate, LRFD+ASD"
      evidence: "packages/kerf-structural/src/kerf_structural/connections.py"

  - domain: D1
    feature: "Constraint sketcher (geo + dim)"
    competitor:
      status: no
      note: "solver only — no CAD or sketcher"
      source: "http://www.calculix.de/"
    kerf:
      status: yes
      note: "PlaneGCS WASM; geo + dim constraints"
      evidence: "src/components/Sketcher.jsx"

  - domain: D1
    feature: "B-rep booleans (general NURBS)"
    competitor:
      status: no
      note: "no geometry kernel; pre-processor must supply mesh"
      source: "http://www.calculix.de/"
    kerf:
      status: yes
      note: "OCCT B-rep booleans"
      evidence: "packages/kerf-occt/src/occt_bridge.py"

  - domain: D1
    feature: "Assemblies — mates"
    competitor:
      status: no
      note: "no assembly or mate system"
      source: "http://www.calculix.de/"
    kerf:
      status: yes
      note: "coincident/concentric/parallel/+BOM panel"
      evidence: "src/components/AssemblyView.jsx"

  - domain: D7
    feature: "3-axis CAM (profile/contour/pocket/face)"
    competitor:
      status: no
      note: "FEA solver only — no CAM capability"
      source: "http://www.calculix.de/"
    kerf:
      status: yes
      note: "CAMView wired; opencamlib backend"
      evidence: "src/components/CAMView.jsx"

  - domain: D4
    feature: "CFD"
    competitor:
      status: no
      note: "structural/thermal FEA only; no fluid solver"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "OpenFOAM bridge (needs install)"
      evidence: "packages/kerf-cfd/src/kerf_cfd/openfoam_bridge.py"

  - domain: D4
    feature: "Thermo cycles (Rankine/Brayton/Otto)"
    competitor:
      status: no
      note: "coupled thermo-mechanical only; no cycle analysis"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "Rankine/Brayton/Otto/Diesel cycle analysis"
      evidence: "packages/kerf-thermal/src/kerf_thermal/cycles.py"

  - domain: D14
    feature: "Material selection (Ashby)"
    competitor:
      status: no
      note: "uses material cards for FEA; no Ashby selection logic"
      source: "http://www.dhondt.de/ccx_2.21.pdf"
    kerf:
      status: yes
      note: "200 materials, 14 families, Pareto frontier"
      evidence: "packages/kerf-matsel/src/kerf_matsel/multi_objective.py"

  - domain: D14
    feature: "Should-cost (6 processes, Boothroyd-Dewhurst)"
    competitor:
      status: no
      note: "no cost estimation capability"
      source: "http://www.calculix.de/"
    kerf:
      status: yes
      note: "6-process Boothroyd-Dewhurst should-cost"
      evidence: "packages/kerf-cost/src/kerf_cost/should_cost.py"
---

# Kerf + CalculiX

CalculiX is not a competitor to Kerf. Kerf wraps CalculiX as its structural finite element solver. This page explains what CalculiX does, what Kerf adds on top, and how the two together deliver structural simulation inside the same workspace where you design the part.

## What CalculiX is

CalculiX is an open-source finite element analysis (FEA) package developed by Guido Dhondt and Klaus Wittig at MTU Aero Engines in Munich. It implements a large subset of the Abaqus input format and is capable of:

- Linear and non-linear static analysis
- Linear and non-linear dynamic analysis (explicit + implicit)
- Modal analysis (eigenvalue extraction)
- Thermal analysis (steady-state + transient)
- Coupled thermo-mechanical analysis
- Buckling analysis
- Hyperelastic, elasto-plastic, and creep material models
- Contact mechanics (node-to-face and face-to-face)
- Shell, beam, solid, and axisymmetric elements

CalculiX consists of two programs: `cgx` (a pre/post-processor with a basic GUI) and `ccx` (the solver). It is licensed under GPL and runs on Linux, macOS, and Windows. It does not have a polished GUI — preprocessing requires either `cgx` scripting or a third-party pre-processor (PrePoMax, FreeCAD FEM, Salome).

## Where they converge

Both CalculiX and Kerf are open-source (CalculiX: GPL; Kerf: MIT) and both are used in mechanical engineering contexts. Both target engineers who need structural and thermal FEA without commercial solver licensing costs. CalculiX supports the Abaqus input format; Kerf's FEM integration uses this same input format internally, making the underlying simulation verifiable against Abaqus benchmarks.

## What Kerf adds

Kerf wraps CalculiX's `ccx` solver as its FEM backend and integrates it into the mechanical design workflow:

- **Chat-native FEM setup.** Describe the analysis — "run a static load of 500N on this bracket face with the mounting holes fixed" — and the LLM generates the CalculiX input deck (material definition, boundary conditions, load cards, element type selection, step definition) backed by doc-search against CalculiX documentation.
- **Geometry from the Kerf model.** The OCCT B-rep geometry designed in Kerf is meshed automatically (tetrahedral or shell elements) using the Kerf mesher. No separate geometry export/import is needed — the model and the simulation share the same geometry source.
- **In-browser results.** Von Mises stress, displacement, temperature, and principal stress results are displayed in the Kerf viewport with colour maps, without requiring `cgx` or ParaView.
- **Unified project.** The FEM analysis, the CAD geometry, the drawings, and the PCB design live in one Kerf project with a single cloud-git version history.
- **Python scripting via kerf-sdk.** Parameterise studies — sweep wall thickness, vary material grade, or compare load cases — from a kerf-sdk Python script.

## Where CalculiX is stronger on its own

- **Non-linear depth.** An experienced FEA engineer using CalculiX directly with a hand-crafted input deck has access to the full non-linear solver depth — complex contact, large deformation, explicit dynamics — that Kerf's chat abstraction covers only partially.
- **Custom element formulations.** CalculiX supports user-defined elements (UEL) and materials (UMAT) for specialised material models. Kerf exposes the built-in material library; UMAT support is not currently surfaced.
- **PrePoMax / FreeCAD FEM ecosystem.** PrePoMax is a polished Windows GUI for CalculiX preprocessing that experienced users prefer for complex analyses. Kerf's mesher is general-purpose.
- **Benchmark and validation depth.** CalculiX has been validated against NAFEMS benchmarks and published literature. Kerf's integration inherits this validation for the covered analysis types.

## Feature matrix

| Feature | Kerf | CalculiX (standalone) |
|---|---|---|
| License | MIT (Kerf) + GPL (CalculiX) | GPL |
| Interface | Chat-native + Python SDK + in-browser results | cgx CLI / PrePoMax / FreeCAD FEM |
| Linear static FEA | Yes | Yes |
| Non-linear static FEA | Selected cases | Full (large deformation, contact) |
| Modal analysis | Yes | Yes |
| Thermal / thermo-mechanical | Yes | Yes |
| Buckling analysis | Yes (linear eigenvalue, Euler-Bernoulli Kg; backend) | Yes |
| Explicit dynamics | Roadmap | Yes |
| Abaqus input format | Yes (internally) | Yes (primary format) |
| UMAT (user materials) | Not yet | Yes |
| Meshing | Integrated OCCT-based mesher | cgx mesher / external (Gmsh, Salome) |
| Geometry source | Kerf 3D model (OCCT) | External STL / BREP / step |
| Results viewer | In-browser (stress / displacement) | cgx / ParaView (full-featured) |
| Unified CAD + FEM | Yes | No (requires separate CAD tool) |
| Python scripting | kerf-sdk on PyPI | Python ccx wrappers (community) |
| NAFEMS benchmarks | Inherited from CalculiX | Directly validated |
| Open source | Yes (MIT + GPL) | Yes (GPL) |

## Both produce Abaqus-format results

CalculiX and Kerf's CalculiX integration both produce output in CalculiX's native `.frd` format (compatible with `cgx`) and optionally in VTK for ParaView. An analysis set up via Kerf's chat interface produces the identical solver output as a hand-crafted CalculiX run — the results files are standard CalculiX, not proprietary. Export the `.inp` and `.frd` files and open them in PrePoMax or `cgx` for deeper post-processing.

---
*Last reviewed: 2026-05-19. CalculiX information sourced from calculix.de and the CalculiX documentation. Kerf capabilities reflect the current shipped product.*
