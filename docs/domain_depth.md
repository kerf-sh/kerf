# Domain Depth — Feature Parity Tracker

Grounded, checkbox-tracked comparison of Kerf's feature depth against
professional CAD/CAE/EDA tools, organised by engineering domain.

Built from the 2026-05-24 multi-agent depth audit (which read the actual module
code), cross-checked against `docs/wiring-audit.md` and the React app in `src/`.

## Legend

- `[x]` — Kerf has a working equivalent (verified against code)
- `[~]` — Partial / basic implementation, not at professional parity
- `[ ]` — Missing / planned

A trailing **(backend)** tag means the engine exists but is **not usable from
the browser UI** — it's callable only as an LLM/agent tool or HTTP route with no
panel. End-user parity needs both the engine *and* a UI surface.

## Headline finding

The engines are **textbook-to-deep** across nearly every domain, but outside
**core CAD, jewelry, ECAD, PLC/firmware**, almost everything is **backend/LLM-tool
only** — no interactive UI. The single biggest parity lever is **surfacing
existing engines in the UI**, second is closing specific depth gaps (real fluid
properties, native plate/shell FE, frame analysis, IBIS/load-flow, etc.).

## Reference tools per domain

| Domain | Compared against |
|---|---|
| D1 Mechanical CAD | SolidWorks, Fusion 360, Onshape, NX, CATIA, Creo, Inventor |
| D2 Structural/FEA | RISA, SAP2000, STAAD, ANSYS Mechanical |
| D3 Machine elements | KISSsoft, Shigley/Roark |
| D4 Thermal/fluid/HVAC | Fusion CFD, ANSYS Fluent, Trane, AFT Fathom |
| D5 Aero/marine/space | XFLR5, Star-CCM+, Orca3D, GMAT, OpenRocket |
| D6 Electronics/EDA/silicon | Altium, KiCad, Cadence, Synopsys, OpenROAD |
| D7 Manufacturing/CAM | Fusion CAM, Mastercam, Cura, Moldflow |
| D8 Civil/geo | Civil 3D, OpenRoads, PLAXIS |
| D9 Dynamics/controls | Adams, Simulink, RoboDK |
| D10 Electrical/energy/PLC | ETAP, PVsyst, CODESYS, PlatformIO |
| D11 Tolerancing/QA | DimXpert, CETOL, PC-DMIS, Minitab |
| D12 Optics/acoustics | Zemax, COMSOL Acoustics |
| D13 Verticals | MatrixGold, 3Shape, Revit, CLO3D |
| D14 Cost/materials/LCA | aPriori, Granta Selector, SimaPro |

---

## D1 — Geometry & core CAD  · engine ~75% · UI ~65%

Strongest domain. PlaneGCS sketcher + full OCCT feature set are wired in-browser.

| Feature | Kerf | Notes |
|---|---|---|
| Constraint sketcher (geo + dim) | [x] | PlaneGCS WASM; missing collinear, ellipse entity, G2 |
| Pad / pocket / revolve | [x] | OCCT, wired |
| Fillet / chamfer (constant) | [x] | wired |
| Variable-radius fillet | [x] | wired (runtime-probed law binding) |
| Shell / hollow | [x] | wired |
| Sweep (1 & 2 rail) | [x] | `BRepOffsetAPI_MakePipeShell` |
| Loft | [~] | no guide-rail overload in binding |
| Patterns (linear/polar) + mirror | [x] | wired |
| Hole wizard (standards/tapped/cbore) | [ ] | bare cylinder punch only |
| Draft (tapered, B-rep) | [ ] | analytic params only, no `BRepFeat_MakeDPrism` |
| Rib / web (B-rep) | [ ] | analytic only, no `BRepFeat_MakeLinearForm` |
| B-rep booleans (general NURBS) | [x] | OCCT; **no graceful failure handling / fuzzy heal** |
| NURBS surfacing (blend/network/patch) | [~] | math complete; OCCT bindings unconfirmed at build |
| Assemblies — mates | [x] | wired (coincident/concentric/parallel/…); + BOM panel |
| Assembly motion study / interference | [ ] | none |
| 2D drawings (views/dims/sections) | [~] | template-based, not live B-rep projection; no UI panel |
| GD&T on drawings / MBD / PMI | [~] | data model only; no UI |
| Sheet metal | [~] | single flange + unfold + flat DXF; no hem/relief/jog/multi-flange |
| Configurations / family variants | [x] | engine complete; **no UI panel** |
| Direct edit (push-pull) | [~] | planar only; no move/delete-face |
| Persistent face naming | [~] | **two disconnected systems** (Python DAG vs OCCT `faceNaming.js`) |
| Model units system | [ ] | kernel is unitless |

## D2 — Structural / FEA  · engine ~70% · UI ~10%

Solid per-code calculators + real FEM via solver bridges. Almost no UI.

| Feature | Kerf | Notes |
|---|---|---|
| AISC 360-22 steel (members) | [x] (backend) | full Ch. E (compression) + F (LTB W/C/HSS/pipe/angle) + H (combined) + 50-section catalog (kerf-structural/aisc_member.py) |
| AISC steel connections | [x] (backend) | bolts/welds/base-plate, LRFD+ASD |
| ACI 318-19 concrete | [x] (backend) | flexure/shear/PM/dev-length; no punching shear, no torsion |
| NDS 2018 timber | [x] (backend) | full adjustment factors |
| ASCE 7-22 wind (MWFRS+C&C) | [x] (backend) | |
| ASCE 7-22 seismic | [x] (backend) | ELF + RSA (SRSS+CQC) + Newmark time-history (seismic/rsa.py); SDOF 0.07% error |
| ASME VIII pressure vessel | [x] (backend) | |
| API 650 tank | [x] (backend) | incl. seismic annex E |
| Fatigue (S-N, ε-N, rainflow) | [x] (backend) | |
| FE — 1D beam / 2D truss (native) | [x] (backend) | Hermite beam validated vs Roark |
| FE — plate / shell (native) | [x] (backend) | MITC4 (Bathe-Dvorkin) + modal; 1.29% error vs Timoshenko at 16×16 (kerf-fem/plate.py) |
| FE — solid (tet/hex) | [x] (backend) | CalculiX/Mystran/Z88 bridge (needs binary) |
| Modal / buckling / nonlinear | [x] (backend) | consistent-mass modal, Riks, J2 plasticity |
| Frame stiffness assembly (2D/3D) | [x] (backend) | 2D+3D beam-column + ASCE 7 LRFD/ASD combos + story drift (struct/frame.py); machine-precision validated |
| P-delta / 2nd-order | [ ] | θ checked, not amplified |
| Section database | [~] (backend) | only ~12 sections vs 300+ |
| Eurocode design (EC2/3/5/8) | [x] (backend) | full coverage: EC2 concrete + EC3 steel + EC5 timber + EC8 seismic |
| Any structural UI panel | [~] | only `femDisplacement.js` displacement render |

## D3 — Machine elements  · engine ~75% · UI ~0%

Shigley/AGMA/ISO/VDI textbook grade. Entirely backend.

| Feature | Kerf | Notes |
|---|---|---|
| Spur/helical gear rating (AGMA 2001-D04) | [x] (backend) | |
| Gear rating (ISO 6336) | [x] (backend) | Method B + safety factors (gearstrength/iso6336.py); ZH=2.495, ZE=191 √MPa validated |
| Worm / bevel gears | [x] (backend) | AGMA 6022/2003 |
| Planetary / epicyclic gearbox | [x] (backend) | 3 Willis modes + compound + module-select (gearbox/planetary.py); torque identity to 1e-10 |
| Bearings — ISO 281 L10 | [x] (backend) | |
| Bearings — ISO/TS 16281 (misalign/contam) | [x] (backend) | aISO + Lnm modified life (bearings/select.py) |
| Fasteners — VDI 2230 | [x] (backend) | |
| Springs (compr/ext/torsion/Belleville) | [x] (backend) | |
| Belt / chain drives | [x] (backend) | |
| Clutch / brake | [x] (backend) | no thermal/fade |
| Shaft (stress + critical speed) | [x] (backend) | closed-form; no stepped-shaft FEA |
| Journal-bearing lubrication | [~] (backend) | simplified Sommerfeld |
| Crane / conveyor / elevator / rigging | [x] (backend) | |
| Any machine-elements UI | [ ] | none |

## D4 — Thermal / fluid / HVAC  · engine ~65% · UI ~15%

Calculators solid; fluid-property fidelity is the weak point.

| Feature | Kerf | Notes |
|---|---|---|
| Psychrometrics (moist air) | [x] (backend) | ASHRAE-grade |
| Heat exchangers (LMTD + ε-NTU) | [x] (backend) | no Bell-Delaware/Kern bundle sizing |
| HVAC duct sizing (SMACNA) | [x] (backend) | + flat-pattern |
| Building loads | [x] (backend) | degree-day + CLTD/RTS transient (ASHRAE Ch.18) + Sol-air + fenestration (buildingenergy/transient.py) |
| Pipe network (Hardy-Cross) | [x] (backend) | clean-water |
| Steam/water properties | [~] (backend) | Antoine fit ±0.3K, **not IAPWS-IF97**; no superheated |
| Refrigerant properties | [~] (backend) | 2-point Antoine; no subcooled/superheated, no glide |
| Thermo cycles (Rankine/Brayton/Otto) | [x] (backend) | |
| Waterhammer (Joukowsky/MOC) | [x] (backend) | |
| CFD | [x] (backend) | **real OpenFOAM** bridge (needs install) |
| Any thermal/fluid UI | [~] | building-energy LLM tools; no panels |

## D5 — Aero / marine / space  · engine ~80% · UI ~40%

Genuinely deep; mostly exposed as LLM tools, no graphical panels.

| Feature | Kerf | Notes |
|---|---|---|
| Standard atmosphere (USSA76) | [x] | wired tool |
| Airfoil geometry (NACA 4/5) | [x] | wired |
| Airfoil inviscid CL (panel) | [x] | wired |
| Airfoil viscous Cd (XFOIL-class) | [x] | wired (Squire-Young; NACA0012 Re=1e6 α=4° → Cd=0.0107) |
| 3D wing VLM (+ viscous + compressibility) | [x] | + strip viscous CD0 + PG/KT compressibility + Korn-Lock wave-drag (vlm_viscous.py); PG 1.401× exact |
| Doublet-lattice / flutter | [x] (backend) | |
| 6-DOF flight dynamics + stability derivs | [x] (backend) | |
| Orbital (Kepler, J2/J3, Hohmann) | [x] | wired |
| Lambert solver | [x] | multi-rev (Lancaster-Blanchard / Izzo 2015); sub-mm propagation residual on N=1, N=2 |
| Reentry / TPS | [x] | wired |
| Propulsion (Tsiolkovsky/staging/CEA-lite) | [x] | wired |
| Turbomachinery / wind-turbine BEM | [x] (backend) | |
| Naval hydrostatics + GZ stability (IMO) | [x] | wired marine tools |
| Seakeeping / RAOs (strip theory) | [x] (backend) | Lewis-form STF + JONSWAP (kerf-marine/seakeeping.py); Wigley validated |
| Graphical aero/marine panels | [ ] | tools-only |

## D6 — Electronics / EDA / silicon  · engine ~75% · UI ~40%

ECAD viewers + SPICE wired; analysis suites + silicon are backend-only.

| Feature | Kerf | Notes |
|---|---|---|
| Schematic capture (KiCad round-trip, ERC) | [x] | viewer wired (read-only) |
| PCB layout (tscircuit, KiCad round-trip) | [x] | viewer wired (read-only) |
| Interactive PCB editing (route/place) | [ ] | view-only; no cursor editing |
| Autoroute (FreeRouting) | [~] | JAR **SHA unpinned → blocked** until set |
| SPICE | [x] | **real ngspice**, wired; binary `.raw` not parsed |
| Signal integrity (Z0/crosstalk/eye/IBIS) | [x] (backend) | + IBIS 5.1 parser + Bergeron channel + PRBS eye envelope (si/ibis_*.py) |
| EMC (radiated/shielding/limits) | [x] (backend) | closed-form; no full-wave |
| PDN (DC IR-drop + AC sweep) | [x] (backend) | + frequency-domain Z(ω) + target-Z + decap optimiser (pdn/ac_impedance.py) |
| PCB thermal | [~] (backend) | lumped Rθ |
| Antenna / link budget | [x] (backend) | |
| DRC / ERC | [x] | DRC overlay wired |
| Battery/BMS, motor/gate/LED driver | [x] (backend) | sizing calculators |
| Silicon synth (Yosys) / STA / GDS / DRC / LVS / formal / CTS | [x] (backend) | deep; **zero UI** |
| Silicon P&R (OpenLane) | [x] (backend) | needs install |
| Analog PVT-corner sim | [x] (backend) | 60 corners (5P×3V×4T) + MC per corner; bandgap ±31mV, Pelgrom σ matched (silicon/analog/pvt.py) |

## D7 — Manufacturing / CAM  · engine ~65% · UI ~35%

Real toolpaths via opencamlib; CAMView wired for common ops.

| Feature | Kerf | Notes |
|---|---|---|
| 3-axis CAM (profile/contour/pocket/face) | [x] | CAMView wired |
| 3D parallel / waterline | [~] | backend; not in UI |
| Adaptive / trochoidal clearing | [x] (backend) | iterative offset + 50% trochoid overlap; engagement on target (kerf-cam/adaptive.py) |
| Rest machining | [x] (backend) | grid-based uncleared-region detection (kerf-cam/adaptive.py) |
| 5-axis (kinematics + posts) | [~] (backend) | engine solid; no UI |
| Turning cycles (G71/G70/threading) | [x] (backend) | |
| G-code post (Fanuc/GRBL/LinuxCNC/Mach3) | [x] | no G41/42 cutter-comp |
| Feeds & speeds + tool-life | [x] (backend) | + Taylor extended (vcT^n·f^a·dp^b=C) + Gilbert economic speed (cuttingtool/tool_life.py) |
| Moldflow / fill sim | [x] (backend) | + Hele-Shaw front tracking + weld-line + air-trap detection (moldflow/flow_front.py) |
| DFM checks | [~] (backend) | mesh-based |
| Nesting | [~] (backend) | skyline bbox; no true-shape NFP |
| Additive / DFAM | [x] (backend) | |
| Injection / forming | [x] (backend) | |
| FDM slicing (Cura) | [x] | wired (PrintSliceView) |

## D8 — Civil / infrastructure / geo  · engine ~75% · UI ~5%

Strong engines; UI is marketing landing only.

| Feature | Kerf | Notes |
|---|---|---|
| Horizontal+vertical alignment (clothoid, SSD) | [x] (backend) | |
| Superelevation runoff transition | [x] (backend) | AASHTO Exhibit 3-20 + 2/3-1/3 distribution + corridor templates (kerf-civil/superelevation.py); 50mph 6% = 144ft validated |
| 3D alignment coordinates (P(station)→xy) | [ ] | scalars only, no plan export |
| Corridor / cross-section | [x] (backend) | divided highway + reverse-crown + urban curb-gutter templates |
| Pavement design (AASHTO '93) | [x] (backend) | deep |
| Survey / COGO | [x] (backend) | traverse adjust, resection |
| Geodesy / projections (Vincenty, TM, UTM, LCC) | [x] (backend) | deep |
| Geotech (bearing/settlement/slope/pile/liquefaction) | [x] (backend) | + Seed-Idriss CSR + SPT/CPT CRR + Tokimatsu (geotech/liquefaction.py); Loma Prieta validated |
| Hydrology (rational/SCS/TR-55) | [x] (backend) | no 2D/unsteady |
| Spillway / dam / railway / earthworks | [x] (backend) | |
| Any civil UI | [ ] | landing page only |

## D9 — Dynamics / motion / controls  · engine ~55% · UI ~5%

Classical foundations solid; modern/3D pieces missing.

| Feature | Kerf | Notes |
|---|---|---|
| Planar MBD (Lagrange/DAE, Baumgarte) | [x] (backend) | |
| 3D MBD with constraint enforcement | [~] (backend) | joints defined but integrator unconstrained |
| Contact / collision dynamics | [x] (backend) | sphere/plane/sphere/mesh + Hunt-Crossley + Coulomb + impulse-restitution (kerf-motion/contact.py); bounce 0.15% error |
| Kinematics (four-bar/slider-crank/cam) | [x] (backend) | |
| Robotics FK/IK (planar) | [x] (backend) | |
| Robotics 6-DOF spatial IK | [x] (backend) | DLS Jacobian (robotics/arm.py), PUMA-class validated |
| Vibration SDOF | [x] (backend) | deep |
| Vibration n-DOF modal / FRF | [x] (backend) | full n-DOF eigen + FRF matrix (vibration/mdof.py) |
| Rotating-machinery balance | [x] (backend) | |
| Controls — classical (Routh/Bode/RL/PID tune) | [x] (backend) | |
| Controls — state-space / LQR / Kalman | [x] (backend) | Ackermann + LQR (CARE) + Luenberger (controls/statespace.py) |
| Controls — discrete / digital | [x] (backend) | c2d ZOH + digital PID |
| System sim (Modelica DAE) | [x] (backend) | 16 extended components (mech/hyd/pneu/thermal/control); MSD + pump-tank + ε-NTU validated |
| Any dynamics UI | [ ] | landing page only |

## D10 — Electrical / energy / PLC / firmware  · engine ~75% · UI ~50%

PLC + firmware + wiring genuinely usable; power/solar backend-only.

| Feature | Kerf | Notes |
|---|---|---|
| NEC power distribution + point-to-point SC | [x] (backend) | deep |
| AC load-flow (Ybus / Newton-Raphson) | [x] (backend) | full polar-form NR (elecpower/loadflow.py); 3+5-bus validated |
| Protection coordination (TCC) / arc-flash | [x] (backend) | IEEE C37.112 U1-U5 + IEEE 1584-2018 incident energy |
| Solar PV (system + partial shading) | [x] (backend) | + single-diode + bypass-diode IV + global MPPT + mismatch loss (solarpv/shading.py); 60-cell P=255W validated |
| Wiring/harness (WireViz + 3D router) | [x] | WiringView wired |
| PLC IEC 61131-3 (ST/Ladder/FB/motion) | [x] | ST editor + **live Ladder power-flow sim** wired |
| Firmware build/upload/monitor/debug | [x] | FirmwareActions + debug panel wired |
| OTA delivery endpoint (cloud) | [ ] | C libs present; server side not wired |

## D11 — Tolerancing / metrology / QA  · engine ~65% · UI ~10%

| Feature | Kerf | Notes |
|---|---|---|
| GD&T data model (ASME Y14.5) | [x] (backend) | no MBD/PMI on model |
| Auto GD&T callout proposal | [x] (backend) | |
| Limits & fits (ISO 286) | [x] (backend) | |
| Tolerance stackup — 1D (WC/RSS/MC) | [x] (backend) | Monte-Carlo LCG bug to fix |
| Tolerance stackup — 3D vector loop | [x] (backend) | 6-DOF vector loop + sensitivity Jacobian (tolstack/tol3d.py) |
| CMM fitting & evaluation | [x] (backend) | |
| Process capability (Cpk/Ppk) | [x] (backend) | |
| SPC control charts (Shewhart/CUSUM/EWMA) | [x] (backend) | + Nelson/WECO run rules (spc/charts.py) |
| Reliability (FMEA/MTBF) | [x] (backend) | |

## D12 — Optics / acoustics  · engine ~55% · UI ~10%

| Feature | Kerf | Notes |
|---|---|---|
| Paraxial ABCD ray transfer | [x] (backend) | |
| Seidel aberrations | [x] (backend) | corrected S5 = p³(n+1)/(2n·f) (2026-05-24) |
| Lensmaker / thick lens / Airy / Snell | [x] (backend) | |
| Non-sequential ray tracing (stray light) | [x] (backend) | Fresnel-split traversal + ghost detection (kerf-optics/nonsequential.py); 0.01% ghost fraction validated |
| Gaussian beam propagation (M², q-param) | [x] (backend) | complex-q + ABCD + M² + fibre coupling (kerf-optics/gaussian.py); HeNe zR=4.96m validated |
| Wave optics / diffraction / polarisation | [ ] | |
| Photonics (LED/photodiode/TIA/fibre) | [x] (backend) | |
| Acoustics (ISO 9613, RT60, weighting, mass-law TL) | [x] (backend) | TL clamped ≥0 (2026-05-24 fix) |
| Wave-domain room acoustics / SEA | [x] (backend) | image-source IR + Schroeder RT60 + modes + SEA (acoustics/wave.py); 3.1% error vs Sabine |

## D13 — Verticals  · engine ~60% · UI ~40%

| Vertical | Kerf | Notes |
|---|---|---|
| Jewelry (41 modules) | [x] | **deep**, full configurator UI — RhinoGold/Matrix-class |
| BIM (walls/slabs/framing/stairs/IFC4) | [x] | Revit-comparable engine + viewer wired via /compile-ifc (visual QA pending) |
| Textiles (weave/knit/drape/cut-room) | [x] (backend) | textiles page; no 3D avatar drape |
| Packaging (ECMA dieline/fold) | [x] (backend) | page; no BCT structural |
| Woodworking (cut-list/joinery/grain) | [~] | page |
| Dental (crown/surgical guide/DICOM) | [~] | spotlight; **crown is placeholder cylinder** |
| Horology (gear train) | [~] | spotlight; no escapement/spring |
| Apparel (blocks/grading/marker) | [~] (backend) | no UI route |
| Interior (space planning/clearance) | [~] (backend) | no UI route |
| Landscape (drainage/grading/planting) | [~] (backend) | no UI route |

## D14 — Cost / materials / LCA  · engine ~70% · UI ~5%

| Feature | Kerf | Notes |
|---|---|---|
| Should-cost (6 processes, Boothroyd-Dewhurst) | [x] (backend) | |
| RFQ quoting (geometry-driven) | [x] (backend) | |
| Process simulation (moldflow/weld/AM/forming) | [x] (backend) | deep |
| Material selection (Ashby) | [x] (backend) | 200 materials (14 families) + Pareto frontier + weighted-score (matsel/multi_objective.py) |
| LCA (full ISO 14040/44 4 phases) | [x] (backend) | use+transport+EoL + multi-impact (acid/eutroph/CTUh/water/PM2.5) + uncertainty (kerf-lca/phases.py) |
| Ergonomics (RULA/REBA) | [x] (backend) | |
| Any cost/materials UI | [ ] | agent tools only |

---

## Cross-cutting priorities (ranked feature-add backlog)

**Tier 1 — surface existing engines in the UI (highest ROI, engines already built):**
1. Fix `BIMView` null feed (Editor.jsx:1960) — Revit-class engine, viewer is one line from working.
2. Wire viscous airfoil Cd into `aero_airfoil_polar` (engine exists, returns placeholder drag).
3. Analysis panels for the deep backend engines: structural (per-code checks), machine elements, SI/EMC/PDN, power/solar, civil, dynamics — even simple form+result panels unlock huge latent value.
4. Silicon flow viewer (synth/STA/GDS) — deep engine, zero UI.

**Tier 2 — close specific depth gaps:**
5. Real fluid properties (IAPWS-IF97 steam + CoolProp refrigerants).
6. Native plate/shell FE element + frame stiffness assembly (structural).
7. Multi-rev Lambert; seakeeping/RAOs (aero/marine).
8. Adaptive/rest-machining CAM; G41/42 cutter-comp.
9. AC load-flow + protection coordination (electrical).
10. State-space/LQR + n-DOF FRF + 6-DOF IK (dynamics/controls).
11. 3D tolerance stackup + SPC charts (QA).
12. ISO 6336 gears + ISO/TS 16281 bearings (machine).

**Tier 3 — correctness fixes (from audit):**
- Optics Seidel S5=0, acoustics mass-law negative TL, dental placeholder crown,
  gcode multi-G-per-block, tolstack Monte-Carlo LCG IndexError risk,
  DFM lone-numpy dependency, FreeRouting unpinned SHA, ngspice binary `.raw`,
  Python-DAG ↔ OCCT face-naming reconciliation.

---

## Parity snapshot (indicative, 2026-05-24)

| Domain | Engine | UI | One-line |
|---|---|---|---|
| D1 Geometry/CAD | ~75% | ~65% | core wired; advanced surf/booleans binding-gated |
| D2 Structural/FEA | ~70% | ~10% | codes deep + FEM bridge; no native frame/plate, no UI |
| D3 Machine elements | ~75% | ~0% | Shigley/AGMA grade; entirely backend |
| D4 Thermal/fluid | ~65% | ~15% | calculators solid; fluid props shallow |
| D5 Aero/marine/space | ~80% | ~40% | deep; LLM-tool surface, no panels |
| D6 Electronics/silicon | ~75% | ~40% | ECAD+SPICE wired; analysis+silicon backend |
| D7 Manufacturing/CAM | ~65% | ~35% | real toolpaths; missing HSM/rest |
| D8 Civil/geo | ~75% | ~5% | strong engines; landing-page UI |
| D9 Dynamics/controls | ~55% | ~5% | classical only; no modern/3D |
| D10 Electrical/PLC/fw | ~75% | ~50% | PLC+firmware usable; power backend |
| D11 Tolerancing/QA | ~65% | ~10% | 1D stack + GD&T model; no 3D/SPC |
| D12 Optics/acoustics | ~55% | ~10% | paraxial+acoustic calc; no NSC/wave |
| D13 Verticals | ~60% | ~40% | jewelry/BIM deep; rest thin |
| D14 Cost/materials | ~70% | ~5% | should-cost deep; agent-only |

*Percentages are indicative engineering judgement from the depth audit, not a
formal metric. Update rows in the same PR as the corresponding code change.*
