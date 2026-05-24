---
slug: catia
competitor: Dassault CATIA
category: cad-mechanical
left: kerf
right: catia
hero_tagline: "CATIA built the A380 — Kerf builds the next generation of engineers who work without seat fees."
reviewed_at: 2026-05-24
features:
  # ── D1 Geometry & core CAD ──────────────────────────────────────────────────
  - domain: D1
    feature: Constraint sketcher (geo + dim)
    competitor: { status: yes, note: "CATIA Sketcher — mature, full geometric + dimensional constraints", source: "https://www.3ds.com/products/catia/sketcher" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Pad / pocket / revolve
    competitor: { status: yes, note: "Part Design workbench — industrial standard", source: "https://www.3ds.com/products/catia/part-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Fillet / chamfer (constant)
    competitor: { status: yes, note: "Part Design dress-up features", source: "https://www.3ds.com/products/catia/part-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Variable-radius fillet
    competitor: { status: yes, note: "Variable-radius edge fillet in Part Design", source: "https://www.3ds.com/products/catia/part-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Shell / hollow
    competitor: { status: yes, note: "Shell command in Part Design", source: "https://www.3ds.com/products/catia/part-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Sweep (1 & 2 rail)
    competitor: { status: yes, note: "Generative Shape Design sweep", source: "https://www.3ds.com/products/catia/generative-shape-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Loft
    competitor: { status: yes, note: "Multi-section solid / loft in Part Design and GSD", source: "https://www.3ds.com/products/catia/part-design" }
    kerf: { status: partial, note: "No guide-rail overload in binding", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: NURBS surfacing (blend/network/patch)
    competitor: { status: yes, note: "FreeStyle Shaper + GSD — Class-A surfaces, G2/G3 continuity, curvature combs, highlight analysis; industry gold standard", source: "https://www.3ds.com/products/catia/freestyle" }
    kerf: { status: partial, note: "Math complete; OCCT bindings unconfirmed at build", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Assemblies — mates
    competitor: { status: yes, note: "Assembly Design — coincident, offset, angle, user-defined constraints", source: "https://www.3ds.com/products/catia/assembly-design" }
    kerf: { status: yes, evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Assembly motion study / interference
    competitor: { status: yes, note: "DMU Kinematics + DMU Space Analysis — envelope sweeps, clash/clearance/contact", source: "https://www.3ds.com/products/catia/dmu-kinematics" }
    kerf: { status: no, evidence: "docs/domain_depth.md — D1 row: Assembly motion study / interference: [ ]" }

  - domain: D1
    feature: 2D drawings (views/dims/sections)
    competitor: { status: yes, note: "Drafting workbench — view generation, dimensions, sections, GD&T callouts", source: "https://www.3ds.com/products/catia/drafting" }
    kerf: { status: partial, note: "Template-based, not live B-rep projection; no UI panel", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: GD&T on drawings / MBD / PMI
    competitor: { status: yes, note: "Functional Tolerancing & Annotation (FTA) — full ISO / ASME PMI on 3D model; 3DEXPERIENCE MBD", source: "https://www.3ds.com/products/catia/functional-tolerancing-and-annotation" }
    kerf: { status: partial, note: "Data model only; no UI panel", evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py" }

  - domain: D1
    feature: Sheet metal
    competitor: { status: yes, note: "Generative Sheetmetal Design — flanges, rip, flat pattern, DXF", source: "https://www.3ds.com/products/catia/generative-sheetmetal-design" }
    kerf: { status: partial, note: "Single flange + unfold + flat DXF; no hem/relief/jog/multi-flange", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D1
    feature: Configurations / family variants
    competitor: { status: yes, note: "Product configurations in Assembly Design + 3DEXPERIENCE effectivity", source: "https://www.3ds.com/products/catia/assembly-design" }
    kerf: { status: yes, note: "Engine complete; no UI panel", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  # ── D2 Structural / FEA ─────────────────────────────────────────────────────
  - domain: D2
    feature: FE — solid (tet/hex)
    competitor: { status: paid, note: "CATIA Simulation / SIMULIA Structural Analysis — Abaqus-class solid meshing; separate paid add-in or 3DEXPERIENCE role", source: "https://www.3ds.com/products/simulia/structural-simulation" }
    kerf: { status: partial, note: "CalculiX/Mystran/Z88 bridge (needs binary); backend only", evidence: "packages/kerf-fem/src/kerf_fem/worker.py" }

  - domain: D2
    feature: FE — plate / shell (native)
    competitor: { status: paid, note: "SIMULIA includes shell elements; paid add-in", source: "https://www.3ds.com/products/simulia/structural-simulation" }
    kerf: { status: yes, note: "MITC4 (Bathe-Dvorkin) + modal; backend only", evidence: "packages/kerf-fem/src/kerf_fem/plate.py" }

  - domain: D2
    feature: Modal / buckling / nonlinear
    competitor: { status: paid, note: "SIMULIA Abaqus — frequency, Riks arc-length, nonlinear plasticity; paid", source: "https://www.3ds.com/products/simulia" }
    kerf: { status: yes, note: "Consistent-mass modal, Riks, J2 plasticity; backend only", evidence: "packages/kerf-fem/src/kerf_fem/nonlinear.py" }

  - domain: D2
    feature: Fatigue (S-N, ε-N, rainflow)
    competitor: { status: paid, note: "fe-safe / SIMULIA — world-class fatigue; paid add-in", source: "https://www.3ds.com/products/simulia/fe-safe" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py" }

  - domain: D2
    feature: AISC 360-22 steel (members)
    competitor: { status: no, note: "CATIA/3DEXPERIENCE has no built-in AISC code-check; requires SIMULIA or third-party", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Full Ch. E/F/H + 50-section catalog; backend only", evidence: "packages/kerf-structural/src/kerf_structural/aisc_member.py" }

  # ── D3 Machine elements ──────────────────────────────────────────────────────
  - domain: D3
    feature: Spur/helical gear rating (AGMA 2001-D04)
    competitor: { status: no, note: "CATIA has no built-in AGMA gear rating; geometry only via GSD", source: "https://www.3ds.com/products/catia/generative-shape-design" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D3
    feature: Bearings — ISO 281 L10
    competitor: { status: no, note: "No built-in bearing life calculator in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D3
    feature: Shaft (stress + critical speed)
    competitor: { status: no, note: "No built-in shaft design calculator in CATIA V5/3DEXPERIENCE", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Closed-form; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  # ── D5 Aero / marine / space ─────────────────────────────────────────────────
  - domain: D5
    feature: 3D wing VLM (+ viscous + compressibility)
    competitor: { status: no, note: "CATIA has no built-in VLM; aerodynamics requires SIMULIA or external tools", source: "https://www.3ds.com/products/simulia" }
    kerf: { status: yes, note: "Strip viscous CD0 + PG/KT compressibility + Korn-Lock wave-drag; wired tool", evidence: "packages/kerf-aero/src/kerf_aero/vlm_viscous.py" }

  - domain: D5
    feature: Doublet-lattice / flutter
    competitor: { status: paid, note: "SIMULIA structural + aerodynamic coupling for flutter; paid add-in", source: "https://www.3ds.com/products/simulia/structural-simulation" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-aero/src/kerf_aero/flutter_pk.py" }

  - domain: D5
    feature: Composites layup (CLT / drape / failure)
    competitor: { status: paid, note: "CATIA Composite Design — ply table, draping, Tsai-Wu failure; core aerospace differentiator; separate license", source: "https://www.3ds.com/products/catia/composites-design" }
    kerf: { status: yes, note: "CLT + drape + Tsai-Wu/Hill/Hashin + interlaminar; backend only", evidence: "packages/kerf-composites/src/kerf_composites/clt.py" }

  - domain: D5
    feature: 6-DOF flight dynamics + stability derivs
    competitor: { status: no, note: "No built-in 6-DOF flight dynamics in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-aero/src/kerf_aero/aeroelasticity.py" }

  - domain: D5
    feature: Orbital (Kepler, J2/J3, Hohmann)
    competitor: { status: no, note: "No orbital mechanics in CATIA/3DEXPERIENCE", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Wired tool", evidence: "packages/kerf-aero/src/kerf_aero/vlm_viscous.py" }

  # ── D6 Electronics / EDA / silicon ──────────────────────────────────────────
  - domain: D6
    feature: Schematic capture (KiCad round-trip, ERC)
    competitor: { status: no, note: "CATIA is a pure mechanical tool; PCB/schematic is not included in base offering", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Viewer wired (read-only)", evidence: "src/components/CompareMd.jsx" }

  - domain: D6
    feature: PCB layout (tscircuit, KiCad round-trip)
    competitor: { status: no, note: "No PCB layout in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Viewer wired (read-only)", evidence: "src/components/CompareMd.jsx" }

  - domain: D6
    feature: Signal integrity (Z0/crosstalk/eye/IBIS)
    competitor: { status: no, note: "No SI analysis in CATIA; requires separate EDA tools", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "IBIS 5.1 + Bergeron channel + PRBS eye; backend only", evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py" }

  - domain: D6
    feature: EMC (radiated/shielding/limits)
    competitor: { status: no, note: "No EMC simulation in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Closed-form; backend only", evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py" }

  - domain: D6
    feature: PDN (DC IR-drop + AC sweep)
    competitor: { status: no, note: "No PDN analysis in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Frequency-domain Z(ω) + target-Z + decap optimiser; backend only", evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py" }

  - domain: D6
    feature: Silicon synth (Yosys) / STA / GDS / DRC / LVS
    competitor: { status: no, note: "No silicon design flow in CATIA/3DEXPERIENCE", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Deep; zero UI", evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py" }

  - domain: D6
    feature: Analog PVT-corner sim
    competitor: { status: no, note: "No analog corner simulation in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "60 corners (5P×3V×4T) + MC; backend only", evidence: "packages/kerf-silicon/src/kerf_silicon/analog/pvt.py" }

  # ── D7 Manufacturing / CAM ───────────────────────────────────────────────────
  - domain: D7
    feature: 3-axis CAM (profile/contour/pocket/face)
    competitor: { status: paid, note: "CATIA Prismatic Machining — 2.5-axis; paid workbench", source: "https://www.3ds.com/products/catia/prismatic-machining" }
    kerf: { status: yes, note: "CAMView wired", evidence: "packages/kerf-cam/src/kerf_cam/worker.py" }

  - domain: D7
    feature: 5-axis (kinematics + posts)
    competitor: { status: paid, note: "CATIA Multi-Axis Surface Machining — full 5-axis; paid workbench", source: "https://www.3ds.com/products/catia/multi-axis-surface-machining" }
    kerf: { status: partial, note: "Engine solid; no UI", evidence: "packages/kerf-cam/src/kerf_cam/worker.py" }

  - domain: D7
    feature: Adaptive / trochoidal clearing
    competitor: { status: paid, note: "DELMIA NC Machine Simulation — advanced clearing strategies; paid add-in", source: "https://www.3ds.com/products/delmia/nc-machine-tool-simulation" }
    kerf: { status: yes, note: "Iterative offset + 50% trochoid overlap; backend only", evidence: "packages/kerf-cam/src/kerf_cam/adaptive.py" }

  - domain: D7
    feature: Feeds & speeds + tool-life
    competitor: { status: no, note: "No built-in Taylor tool-life or Gilbert economic speed in CATIA CAM", source: "https://www.3ds.com/products/catia/prismatic-machining" }
    kerf: { status: yes, note: "Taylor extended + Gilbert economic speed; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/cuttingtool/tool_life.py" }

  - domain: D7
    feature: Moldflow / fill sim
    competitor: { status: paid, note: "CATIA Mold Tooling Design (geometry only); full fill simulation requires SIMULIA Plastic; paid", source: "https://www.3ds.com/products/catia/mold-tooling-design" }
    kerf: { status: yes, note: "Hele-Shaw front tracking + weld-line + air-trap; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D7
    feature: Nesting (skyline + true-shape NFP)
    competitor: { status: no, note: "No sheet nesting in CATIA base; requires third-party (e.g. Alma)", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Minkowski-sum NFP + IFP + bottom-left fill; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  - domain: D7
    feature: FDM slicing (Cura)
    competitor: { status: no, note: "No additive slicing in CATIA base", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Wired (PrintSliceView)", evidence: "src/components/CompareMd.jsx" }

  # ── D8 Civil / infrastructure / geo ─────────────────────────────────────────
  - domain: D8
    feature: Horizontal+vertical alignment (clothoid, SSD)
    competitor: { status: no, note: "CATIA has no civil road alignment tools; civil domain is outside its scope", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-civil/src" }

  - domain: D8
    feature: Geotech (bearing/settlement/slope/pile/liquefaction)
    competitor: { status: no, note: "No geotechnical engineering in CATIA/3DEXPERIENCE", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Seed-Idriss CSR + SPT/CPT CRR; backend only", evidence: "packages/kerf-civil/src" }

  # ── D9 Dynamics / motion / controls ─────────────────────────────────────────
  - domain: D9
    feature: Planar MBD (Lagrange/DAE, Baumgarte)
    competitor: { status: paid, note: "CATIA DMU Kinematics — kinematic simulation (mechanism, not fully dynamic); SIMULIA Adams link for full MBD; paid", source: "https://www.3ds.com/products/catia/dmu-kinematics" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-motion/src" }

  - domain: D9
    feature: Kinematics (four-bar/slider-crank/cam)
    competitor: { status: yes, note: "DMU Kinematics — joints, commands, simulation, envelope; core CATIA capability", source: "https://www.3ds.com/products/catia/dmu-kinematics" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-motion/src" }

  - domain: D9
    feature: Controls — state-space / LQR / Kalman
    competitor: { status: no, note: "No built-in controls design in CATIA; requires Simulink or MATLAB co-simulation", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Ackermann + LQR (CARE) + Luenberger; backend only", evidence: "packages/kerf-motion/src" }

  - domain: D9
    feature: System sim (Modelica DAE)
    competitor: { status: paid, note: "CATIA Systems Engineering (SysML/Modelica) — system-level simulation; paid 3DEXPERIENCE role", source: "https://www.3ds.com/products/catia/systems-engineering" }
    kerf: { status: yes, note: "16 extended components (mech/hyd/pneu/thermal/control); backend only", evidence: "packages/kerf-motion/src" }

  # ── D10 Electrical / energy / PLC / firmware ─────────────────────────────────
  - domain: D10
    feature: Wiring/harness (WireViz + 3D router)
    competitor: { status: paid, note: "CATIA Electrical Wire Routing + Electrical Harness Assembly — 3D harness; paid workbenches", source: "https://www.3ds.com/products/catia/electrical-wire-routing" }
    kerf: { status: yes, note: "WiringView wired", evidence: "src/components/CompareMd.jsx" }

  - domain: D10
    feature: PLC IEC 61131-3 (ST/Ladder/FB/motion)
    competitor: { status: no, note: "No PLC programming environment in CATIA; DELMIA covers robot/NC but not IEC 61131 PLC", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "ST editor + live Ladder power-flow sim wired", evidence: "src/components/CompareMd.jsx" }

  - domain: D10
    feature: Solar PV (system + partial shading)
    competitor: { status: no, note: "No solar PV simulation in CATIA/3DEXPERIENCE", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Single-diode + bypass-diode IV + global MPPT + mismatch loss; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  # ── D11 Tolerancing / metrology / QA ────────────────────────────────────────
  - domain: D11
    feature: GD&T data model (ASME Y14.5)
    competitor: { status: yes, note: "FTA (Functional Tolerancing & Annotation) — full PMI / 3D annotations on model; ASME Y14.5 + ISO 1101", source: "https://www.3ds.com/products/catia/functional-tolerancing-and-annotation" }
    kerf: { status: yes, note: "Backend only; no MBD/PMI on model", evidence: "packages/kerf-gdnt/src/kerf_gdnt/feature_control_frame.py" }

  - domain: D11
    feature: Tolerance stackup — 1D (WC/RSS/MC)
    competitor: { status: paid, note: "CATIA Tolerance Analysis — 1D stackup; DELMIA/SIMULIA CETOL for full 3D; paid add-ins", source: "https://www.3ds.com/products/catia/tolerance-analysis" }
    kerf: { status: yes, note: "WC/RSS/MC (Monte-Carlo LCG); backend only", evidence: "packages/kerf-mates/src/kerf_mates/tolerance.py" }

  - domain: D11
    feature: Tolerance stackup — 3D vector loop
    competitor: { status: paid, note: "CETOL 6σ (Sigmetrix, 3DEXPERIENCE partner) — 3D statistical tolerance analysis; paid", source: "https://www.3ds.com/3dexperience/marketplace/en/apps/cetol-6sigma" }
    kerf: { status: yes, note: "6-DOF vector loop + sensitivity Jacobian; backend only", evidence: "packages/kerf-mates/src/kerf_mates/tolerance3d.py" }

  - domain: D11
    feature: Process capability (Cpk/Ppk)
    competitor: { status: no, note: "No Cpk/Ppk / SPC in CATIA; requires Quality/MES layer", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Backend only", evidence: "packages/kerf-gdnt/src/kerf_gdnt/inspection_report.py" }

  # ── D13 Verticals ────────────────────────────────────────────────────────────
  - domain: D13
    feature: BIM (walls/slabs/framing/stairs/IFC4)
    competitor: { status: no, note: "CATIA is a mechanical/aerospace tool; BIM/IFC is outside scope (Dassault sells CATIA Architecture separately for concept AEC)", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Revit-comparable engine + viewer wired via /compile-ifc", evidence: "packages/kerf-bim/src" }

  - domain: D13
    feature: Jewelry (41 modules)
    competitor: { status: no, note: "No jewelry design tools in CATIA", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Deep, full configurator UI — RhinoGold/Matrix-class", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }

  # ── D14 Cost / materials / LCA ───────────────────────────────────────────────
  - domain: D14
    feature: Should-cost (6 processes, Boothroyd-Dewhurst)
    competitor: { status: paid, note: "3DEXPERIENCE DELMIA Manufacturing Cost Estimation — process-based costing; paid role", source: "https://www.3ds.com/products/delmia/manufacturing-cost-estimation" }
    kerf: { status: yes, note: "6 processes, Boothroyd-Dewhurst; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/costing/estimate.py" }

  - domain: D14
    feature: Material selection (Ashby)
    competitor: { status: paid, note: "3DEXPERIENCE GRANTA MI (Granta Design) — material database + Ashby charts; separate enterprise licence", source: "https://www.3ds.com/products/granta" }
    kerf: { status: yes, note: "200 materials (14 families) + Pareto frontier + weighted-score; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/matsel/multi_objective.py" }

  - domain: D14
    feature: LCA (full ISO 14040/44 4 phases)
    competitor: { status: no, note: "No integrated LCA in CATIA/3DEXPERIENCE base offering; Dassault partners with Ecodesign for Buildings separately", source: "https://www.3ds.com/products/catia" }
    kerf: { status: yes, note: "Full ISO 14040/44 + multi-impact + uncertainty; backend only", evidence: "packages/kerf-lca/src/kerf_lca/phases.py" }

  - domain: D14
    feature: Process simulation (moldflow/weld/AM/forming)
    competitor: { status: paid, note: "SIMULIA Plastic for injection moulding; CATIA Composites for layup process; paid add-ins", source: "https://www.3ds.com/products/simulia" }
    kerf: { status: yes, note: "Moldflow Hele-Shaw + weld/AM/forming calculators; backend only", evidence: "packages/kerf-cad-core/src/kerf_cad_core/plugin.py" }
---

# Kerf vs Dassault CATIA

Dassault CATIA is the gold standard for complex-surface and multi-disciplinary product engineering in automotive and aerospace. Airbus, Boeing, and every major car OEM use CATIA V5 or 3DEXPERIENCE to define their master geometry. It is extraordinarily capable and extraordinarily expensive — six-figure enterprise licensing is common. Kerf is the MIT-licensed, chat-native alternative for the next generation of engineers who cannot or should not pay that freight.

## Where they converge

Both CATIA and Kerf start from a parametric B-rep kernel and a constraint-based sketcher. Both emphasise geometric precision over approximate mesh-based workflows — tolerances matter, and both tools treat the model as the source of truth for downstream fabrication. Both support STEP as the neutral exchange format, which means geometry moves between them without reconstruction.

Both tools also reach across disciplines: CATIA's 3DEXPERIENCE platform wraps mechanical, electrical, simulation, and PLM in one umbrella; Kerf similarly covers parametric mechanical, sheet metal, drawings, PCB electronics, and scripting in a single environment. The philosophy of "one workspace, not a collection of siloed applications" is shared.

Finally, both acknowledge that assembly is central to real engineering. CATIA's product structure with constraints and tolerance analysis, and Kerf's assembly mates, address the same fundamental need: expressing how parts relate, not just how individual parts are shaped.

## Where Kerf wins

- **MIT open-core, zero seat fee.** CATIA licensing starts in the thousands of dollars per seat per year (as of May 2026) and often requires VAR negotiation. Kerf is free locally under MIT — the full feature set runs on a laptop with a single binary install. Teams that cannot justify enterprise CAD spend can do real engineering work with Kerf immediately.
- **Chat-native workflow.** Describe a design intent — "add a 3mm fillet to all concave edges" or "change the flange material to aluminium 6061 and recalculate the flat pattern" — and Kerf's LLM edits the feature tree directly, backed by doc-search so it does not invent surface. No comparable natural-language interface in CATIA has shipped to our knowledge (as of May 2026).
- **BYO LLM / BYO key.** Bring your own Anthropic or OpenAI API key; zero billing flows through Kerf in the `kerf_byo` tier. We're not aware of any configurable LLM in CATIA (as of May 2026).
- **In-box electronics.** CATIA is a pure mechanical tool at its core — PCB schematic, layout, pre-compliance simulation (SI/EMC/PDN/thermal), and fab output are not part of its base offering. Kerf ships all of these without extension gating.
- **Single-binary offline install.** A brew or curl install produces a fully functional offline binary. CATIA requires Windows, a licence server, and a complex installer suite that takes hours. Kerf runs on macOS, Windows, and Linux.

## Where CATIA wins

- **Class-A surface quality.** CATIA's FreeStyle and ICEM Surf workspaces, with their curvature-continuity tools (G2/G3 surface blends, highlight analysis, isophote visualisation), are the industry benchmark for automotive exterior surfacing. Kerf's NURBS Phase 4 is early and does not approach this.
- **Kinematics and DMU.** CATIA's Digital Mock-Up (DMU) Kinematics workbench models complex mechanical linkages, cam followers, and multi-body motion with interference sweeps and envelope computation. Kerf has no kinematic simulation.
- **Multi-physics CAE.** CATIA Simulation, together with SIMULIA Abaqus, provides structural, thermal, fatigue, and crash-analysis workflows that Kerf does not touch. For full-vehicle FEA sign-off, CATIA's ecosystem is irreplaceable.
- **PLM and configuration management.** ENOVIA / 3DEXPERIENCE offers programme-level BOM management, change orders, effectivity, and configuration at a scale that Kerf's cloud git collaboration layer does not target.
- **Industry certification and validation.** Airframe geometry derived in CATIA carries a paper trail from master model to CNC to inspection report that regulatory bodies accept. Kerf has no certification pathway today.

## Feature matrix

| Feature | Kerf | CATIA (3DEXPERIENCE / V5) |
|---|---|---|
| License | MIT open-core | Proprietary enterprise (VAR, six-figure) |
| Cost | Free local; pay-as-you-go hosted credits | Thousands USD/seat/yr (May 2026) |
| Offline / self-host | Full offline single binary | Windows + licence server required |
| Parametric B-rep | OCCT feature tree | CATIA V5 / CGM kernel |
| Constraint sketcher | Sketcher v2 | CATIA Sketcher (mature) |
| Class-A surfacing | NURBS Phase 4 (early) | FreeStyle / ICEM Surf (industry gold standard) |
| Sheet metal | Flange + unfold + flat-pattern DXF | Sheet Metal workbench (mature) |
| Assembly | Assembly mates | Product Structure + Kinematics (mature) |
| Kinematic simulation | Not yet | DMU Kinematics (mature) |
| FEM / structural CAE | Not yet | SIMULIA / CATIA Simulation (deep) |
| PCB / electronics | In-box schematic + layout + pre-compliance | Not included (separate tools) |
| Chat / LLM editing | Chat-native | None known (as of May 2026) |
| Python scripting | kerf-sdk on PyPI | CAA RADE (C++) |
| STEP export | Yes | Yes |
| BIM / IFC | IFC Tier 2 import | Limited |
| Open source | Yes (MIT) | No |

## Both produce STEP

CATIA and Kerf both export ISO 10303 STEP (AP214 / AP242). STEP is the universal handshake between CAD systems, and the fact that both tools produce it means geometry flows cleanly — take a CATIA surface, import it into Kerf for downstream electronics integration or drawing annotation, and move on.

---
*Last reviewed: 2026-05-19. Competitor information sourced from public Dassault Systèmes pricing and product pages. Kerf capabilities reflect the current shipped product.*
