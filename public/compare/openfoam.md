---
slug: openfoam
competitor: OpenFOAM
category: cad-sim
left: kerf
right: openfoam
hero_tagline: "OpenFOAM solves the Navier-Stokes equations — Kerf wraps it so you describe the flow problem in plain language."
reviewed_at: 2026-05-24
features:
  # ── D4 Thermal / fluid / HVAC ──────────────────────────────────────────────
  - domain: D4
    feature: "CFD — incompressible flow"
    competitor:
      status: yes
      note: "simpleFoam, icoFoam, pimpleFoam, pisoFoam RANS/transient solvers"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "OpenFOAM backend bridge; chat-native case generation; needs OpenFOAM install"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — compressible flow"
    competitor:
      status: yes
      note: "rhoCentralFoam, sonicFoam, rhoSimpleFoam for subsonic/transonic/supersonic"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "OpenFOAM backend bridge; core compressible solvers exposed via chat"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — conjugate heat transfer"
    competitor:
      status: yes
      note: "chtMultiRegionFoam, buoyantSimpleFoam, buoyantPimpleFoam"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "OpenFOAM backend bridge; CHT solver accessible via LLM tool"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — multiphase flow"
    competitor:
      status: yes
      note: "interFoam (VOF), twoPhaseEulerFoam, multiphaseInterFoam, cavitatingFoam"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "Selected multiphase solvers via bridge; full multiphase suite requires direct OpenFOAM"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — combustion / reacting flow"
    competitor:
      status: yes
      note: "reactingFoam, fireFoam, XiFoam, PDRFoam for premixed/non-premixed combustion"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: no
      note: "Combustion solvers not yet exposed in Kerf bridge"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — turbulence models (RANS)"
    competitor:
      status: yes
      note: "k-epsilon, k-omega SST, Spalart-Allmaras, realizable k-eps, v2-f, and more"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "k-eps and k-omega SST exposed via chat case generation; full model library via direct OpenFOAM"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — LES / DES / DNS"
    competitor:
      status: yes
      note: "Smagorinsky, WALE, dynamic Smagorinsky LES; DES and SAS-SST; DNS at low Re"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "LES models accessible via bridge; specialist case tuning requires expert review"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — mesh generation (snappyHexMesh)"
    competitor:
      status: yes
      note: "blockMesh + snappyHexMesh + cfMesh; automatic hex-dominant meshing from STL"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "snappyHexMesh dict generated via chat from Kerf STL export; no GUI mesh editor"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — Lagrangian particle tracking"
    competitor:
      status: yes
      note: "lagrangianIntermediate library; DPM, spray, coal, radiation particle types"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: no
      note: "Lagrangian particle models not exposed in Kerf bridge"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — dynamic mesh / FSI"
    competitor:
      status: yes
      note: "dynamicFvMesh, overset mesh, sixDoFRigidBodyMotion for moving-boundary problems"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: no
      note: "Dynamic mesh and FSI not yet exposed in Kerf bridge"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — parallel MPI execution"
    competitor:
      status: yes
      note: "Domain decomposition (scotch/metis/simple) + MPI; petascale on HPC clusters"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "Hosted cloud compute for moderate-scale runs; petascale HPC requires direct OpenFOAM"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "CFD — post-processing (ParaView / VTK)"
    competitor:
      status: yes
      note: "Native ParaView integration via foamToVTK; full field visualization, streamlines, iso-surfaces"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "Basic in-browser result viewer; full ParaView pipeline on exported OpenFOAM case directory"
      evidence: "packages/kerf-cfd/"

  - domain: D4
    feature: "Psychrometrics (moist air)"
    competitor:
      status: no
      note: "OpenFOAM has no dedicated psychrometric calculator; HVAC load calcs are outside scope"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "ASHRAE-grade psychrometrics (backend)"
      evidence: "packages/kerf-hvac/"

  - domain: D4
    feature: "Heat exchanger sizing (LMTD / Bell-Delaware)"
    competitor:
      status: no
      note: "No heat-exchanger design calculator; CHT simulation only"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "LMTD + epsilon-NTU + Bell-Delaware + TEMA layout (backend)"
      evidence: "packages/kerf-hvac/heatxfer/"

  - domain: D4
    feature: "HVAC duct sizing (SMACNA)"
    competitor:
      status: no
      note: "No SMACNA duct-sizing module; full CFD only"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "SMACNA duct sizing + flat-pattern (backend)"
      evidence: "packages/kerf-hvac/"

  - domain: D4
    feature: "Pipe network (Hardy-Cross)"
    competitor:
      status: no
      note: "No pipe-network calculator; internal flow can be simulated but not network-solved"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "Hardy-Cross pipe network solver (backend)"
      evidence: "packages/kerf-hvac/"

  # ── D5 Aero / marine / space ───────────────────────────────────────────────
  - domain: D5
    feature: "External aerodynamics (vehicle / airfoil)"
    competitor:
      status: yes
      note: "simpleFoam + snappyHexMesh standard workflow for automotive/aircraft external aero"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "VLM + viscous Cd + OpenFOAM bridge for full CFD; airfoil panel method wired"
      evidence: "packages/kerf-aero/"

  - domain: D5
    feature: "Wind loading / wind engineering"
    competitor:
      status: yes
      note: "Atmospheric boundary layer profiles + rough-wall functions for wind-load CFD"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "ASCE 7-22 wind (MWFRS+C&C) code calc; full CFD via OpenFOAM bridge"
      evidence: "packages/kerf-structural/"

  - domain: D5
    feature: "Marine / offshore hydrodynamics"
    competitor:
      status: yes
      note: "waves2Foam, olaFlow, interFoam for wave-structure interaction"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: partial
      note: "Hydrostatics + GZ + seakeeping RAOs (strip theory) wired; wave CFD via bridge"
      evidence: "packages/kerf-marine/"

  # ── D7 Manufacturing / CAM ─────────────────────────────────────────────────
  - domain: D7
    feature: "Mold filling / injection simulation"
    competitor:
      status: partial
      note: "interFoam used for mold-fill research; no dedicated Moldflow-equivalent GUI workflow"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "Hele-Shaw flow-front tracking + weld-line + air-trap detection (backend)"
      evidence: "packages/kerf-mfg/moldflow/"

  # ── D1 Geometry / core CAD ─────────────────────────────────────────────────
  - domain: D1
    feature: "CAD geometry modelling"
    competitor:
      status: no
      note: "OpenFOAM has no CAD environment; geometry imported as STL/blockMesh from external tools"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "Full parametric B-rep modeller (OCCT); sketcher + feature tree wired in browser"
      evidence: "src/components/ModellingWorkspace/"

  - domain: D1
    feature: "Unified CAD + simulation project"
    competitor:
      status: no
      note: "Case setup and geometry are separate tools/workflows"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "Single cloud-git project: B-rep model, CFD case, and PCB thermal co-versioned"
      evidence: "packages/kerf-cfd/"

  # ── D2 Structural / FEA ────────────────────────────────────────────────────
  - domain: D2
    feature: "Structural FEA (stress / displacement)"
    competitor:
      status: no
      note: "OpenFOAM has solids4Foam for basic FEA but it is not a primary use case"
      source: "https://www.openfoam.com/documentation/guides/latest/doc/openfoam-guide.html"
    kerf:
      status: yes
      note: "CalculiX/Mystran bridge + native beam/plate FEM; AISC/ACI/NDS code checks (backend)"
      evidence: "packages/kerf-structural/"

  # ── D14 Cost / materials / LCA ─────────────────────────────────────────────
  - domain: D14
    feature: "Open-source licensing"
    competitor:
      status: yes
      note: "GPL v3 — free to use, modify, distribute; no per-seat cost"
      source: "https://www.openfoam.org/licence"
    kerf:
      status: yes
      note: "MIT open-core — engine code MIT; cloud features proprietary"
      evidence: "LICENSE"

  - domain: D14
    feature: "Python scripting / automation API"
    competitor:
      status: partial
      note: "PyFoam and Ofpp provide Python wrappers; no official first-party SDK"
      source: "https://openfoamwiki.net/index.php/Contrib/PyFoam"
    kerf:
      status: yes
      note: "kerf-sdk on PyPI; same API used by chat interface"
      evidence: "packages/kerf-sdk/"
---

# Kerf + OpenFOAM

OpenFOAM is not a competitor to Kerf. It is a complementary open-source CFD (Computational Fluid Dynamics) solver that Kerf integrates with to deliver fluid simulation as part of a unified engineering workflow. This page explains what OpenFOAM does, what Kerf adds on top, and why the combination is more accessible than OpenFOAM alone.

## What OpenFOAM is

OpenFOAM (Open Field Operation And Manipulation) is the world's most widely used open-source CFD framework. Originally developed at Imperial College London and now maintained by the OpenFOAM Foundation and ESI Group (OpenCFD), it provides a C++ library and a collection of solvers covering:

- Incompressible flow (simpleFoam, icoFoam, pimpleFoam)
- Compressible flow (rhoCentralFoam, sonicFoam)
- Heat transfer (buoyantSimpleFoam, chtMultiRegionFoam)
- Multiphase (interFoam, twoPhaseEulerFoam)
- Combustion (reactingFoam, fireFoam)
- Turbulence models (k-ε, k-ω SST, LES, DES)

OpenFOAM is entirely command-line driven — case setup uses text dictionaries (blockMesh, snappyHexMesh, fvSolution, fvSchemes), and results are post-processed with ParaView. It is powerful and free (GPL licensed), but the learning curve for case setup is steep enough that many engineering teams pay for commercial CFD tools just to avoid it.

## Where they converge

Both OpenFOAM and Kerf are open-source tools (OpenFOAM: GPL; Kerf: MIT) used in engineering simulation contexts. Both are used without commercial simulation licensing costs. Both are appropriate for aerospace, automotive, HVAC, thermal management, and marine applications.

## What Kerf adds

Kerf integrates OpenFOAM as a simulation backend, adding:

- **Chat-native case setup.** Describe the flow problem — "simulate airflow around this enclosure at 5 m/s with turbulence intensity 5%" — and the LLM generates the OpenFOAM case dictionary set (blockMeshDict or snappyHexMesh, boundary conditions, solver settings, turbulence model selection) backed by doc-search against the OpenFOAM documentation.
- **Geometry from the Kerf model.** The 3D geometry designed in Kerf's mechanical workspace can be exported directly as the STL surface for snappyHexMesh. No separate geometry pipeline is needed — the design and the simulation share the same geometry source.
- **Unified project.** A Kerf project can contain the mechanical CAD model, the OpenFOAM CFD setup, and the PCB thermal analysis in a single cloud-git-versioned project. Design changes propagate to the simulation mesh automatically.
- **Cloud execution.** OpenFOAM runs on Linux with MPI for parallel execution. Kerf's hosted environment provides cloud compute for CFD runs without requiring the user to set up an HPC environment.
- **Python scripting via kerf-sdk.** Parameterise a CFD sweep — vary inlet velocity, change turbulence model, or sweep geometry parameters — from a kerf-sdk Python script using the same API the chat interface uses.

## Where OpenFOAM is stronger on its own

- **Solver depth and control.** An experienced CFD engineer using OpenFOAM directly with hand-tuned dictionaries and custom boundary conditions has more precision than Kerf's chat abstraction. Kerf's LLM generates correct dictionaries for common cases; exotic multiphase or combustion cases may require expert review.
- **HPC cluster deployment.** Production CFD runs on 100s of cores via MPI decomposition are best managed directly on an HPC cluster with OpenFOAM installed natively. Kerf's cloud compute is appropriate for moderate-scale runs, not petascale.
- **Post-processing with ParaView.** OpenFOAM + ParaView is a complete, highly capable visualisation pipeline. Kerf's built-in result viewer is simpler.
- **Community solvers.** The OpenFOAM ecosystem has hundreds of community-contributed solvers and utilities. Kerf exposes the core solver set; specialised community solvers require direct OpenFOAM access.

## Feature matrix

| Feature | Kerf | OpenFOAM (standalone) |
|---|---|---|
| License | MIT (Kerf) + GPL (OpenFOAM) | GPL |
| Interface | Chat-native + Python SDK | Text dictionary files + CLI |
| Incompressible flow | Yes | Yes (simpleFoam, pimpleFoam, etc.) |
| Compressible flow | Yes | Yes (rhoCentralFoam, sonicFoam) |
| Heat transfer / conjugate | Yes | Yes (chtMultiRegionFoam) |
| Multiphase | Selected solvers | Full multiphase suite |
| Combustion | Roadmap | Yes (reactingFoam, fireFoam) |
| Turbulence models | k-ε, k-ω SST, LES | Full model library |
| Mesh generation | snappyHexMesh via chat | blockMesh + snappyHexMesh (manual) |
| Geometry source | Kerf 3D model (STL export) | External STL / CAD |
| Unified CAD + simulation | Yes | No (requires separate CAD tool) |
| Cloud execution | Yes (hosted) | Requires Linux / HPC |
| HPC / MPI scaling | Moderate (hosted) | Petascale (on cluster) |
| Post-processing | Basic in-browser | ParaView (full-featured) |
| Python scripting | kerf-sdk on PyPI | PyFoam / Ofpp |
| Open source | Yes (MIT + GPL) | Yes (GPL) |

## Both produce OpenFOAM field data (VTK)

OpenFOAM and Kerf's OpenFOAM integration both produce field results in OpenFOAM's native format, convertible to VTK for post-processing in ParaView. A simulation set up via Kerf's chat interface produces the identical case directory structure as a hand-crafted OpenFOAM case — the output is standard OpenFOAM, not a proprietary format. Export the case, open it in ParaView on your local machine, and continue analysis there.

---
*Last reviewed: 2026-05-19. OpenFOAM information sourced from openfoam.org and openfoam.com. Kerf capabilities reflect the current shipped product.*
