---
slug: calculix
competitor: CalculiX
category: cad-sim
left: kerf
right: calculix
hero_tagline: "CalculiX runs the FEM — Kerf wraps it so structural analysis is as easy as describing the load case."
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
| Buckling analysis | Roadmap | Yes |
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
