# Backend Wiring Audit

Snapshot: 2026-05-19.  One row per backend capability.  "Frontend Status" describes
whether a browser-side module / UI panel actively calls the route or compute engine.

Legend:
- **Wired** — frontend module calls route / result is displayed in UI
- **Route exists, no UI** — HTTP endpoint exists but no frontend component consumes it
- **Partial** — some paths wired, others not
- **Bridge only** — JS bridge exists, no React component yet
- **No route** — computation lives in Python but no HTTP endpoint
- **Pending** — route returns `{status:"pending"}` (optional dep not installed)

---

## Aerodynamics / Atmosphere

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / aero | ISA 1976 atmosphere (T, p, ρ, a) | **Route exists, no UI** | `POST /api/aero/atmosphere` — shipped this sweep; bridge not wired to a component |
| kerf-cad-core / aero | Dynamic pressure q=½ρV² | No route | Lives in `kerf_cad_core.aero.flow`; no HTTP endpoint yet |
| kerf-cad-core / aero | Reynolds number | No route | Pure-Python; no route |
| kerf-cad-core / aero | Mach number + Prandtl-Glauert | No route | Pure-Python; no route |
| kerf-cad-core / aero | Thin-airfoil Cl/Cm | **Wired** | `airfoilPolarBridge.js` + `AirfoilPolarPlot.jsx` wired (2026-05-24) |
| kerf-cad-core / aero | Finite-wing CLT (Prandtl lifting line) | No route | Pure-Python |
| kerf-cad-core / aero | Drag buildup CDi, CD, L/D | No route | Pure-Python |
| kerf-cad-core / aero | Level flight T, P, V_stall | No route | Pure-Python |
| kerf-cad-core / aero | Climb rate | No route | Pure-Python |
| kerf-cad-core / aero | Actuator disc / propeller | No route | Pure-Python |
| kerf-cad-core / aero | Breguet range + endurance | No route | Pure-Python |
| kerf-cad-core / windturbine | Wind turbine rotor BEM | No route | `windturbine/` module; no route wired |

---

## Propulsion / Rockets

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-api (new) | Tsiolkovsky Δv | **Route exists, no UI** | `POST /api/aero/propulsion/tsiolkovsky` — shipped this sweep; bridge exists (`aeroPropulsionBridge.js`) |
| kerf-api (new) | CEA-lite Isp lookup | **Route exists, no UI** | `POST /api/aero/propulsion/cea-lite` — lookup table; degrades gracefully without rocketcea |
| kerf-cad-core / combustion | Combustion burn calcs | No route | `combustion/burn.py`; no HTTP endpoint |
| kerf-cad-core / turbo | Turbomachinery stage design | No route | `turbo/tools.py`; no route |
| kerf-cad-core / pressvessel | Pressure vessel design | No route | `pressvessel/`; no route |
| kerf-cad-core / thermocycle | Thermodynamic cycles | No route | `thermocycle/`; no route |

---

## Composites / Structures

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-api (new) | CLT ABD matrix analysis | **Route exists, no UI** | `POST /api/composites/clt` — shipped this sweep |
| kerf-api (new) | Ply failure indices (max-stress, Tsai-Wu, Tsai-Hill) | **Route exists, no UI** | `POST /api/composites/failure` — shipped this sweep |
| kerf-cad-core / composites | Laminate engineering moduli | No route | `laminate_engineering_moduli()`; no route yet |
| kerf-cad-core / composites | First-ply-failure load | No route | `first_ply_failure_load()`; no route yet |
| kerf-cad-core / beam | Beam bending / deflection | No route | `beam/`; no route |
| kerf-cad-core / struct | Structural frame analysis | No route | `struct/`; no route |
| kerf-cad-core / fatigue | Fatigue (S-N curves) | No route | `fatigue/`; no route |
| kerf-cad-core / concrete | Concrete section design | No route | `concrete/`; no route |
| kerf-cad-core / timber | Timber member sizing | No route | `timber/`; no route |
| kerf-cad-core / steelconn | Steel connection checks | No route | `steelconn/`; no route |
| kerf-fem | FEM solver | Partial | `femDisplacement.js` renders displacement; backend route exists in kerf-fem plugin |

---

## Electronics / PCB

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-electronics | PCB autoroute (freerouting) | **Wired** | `POST /api/electronics/autoroute`; `pcbRouting.js` + shove router UI |
| kerf-electronics | Copper pour | **Wired** | `copperPour.js` frontend; pour route in plugin |
| kerf-electronics | SPICE simulation | Partial | `circuitToSpice.js`; backend `routes_spice.py` exists; no results panel |
| kerf-electronics | Signal integrity (SI) | Route exists, no UI | `routes_rf.py`; si/eye module; no frontend |
| kerf-electronics | EMC / EMI | No route | `emc/`; no route |
| kerf-electronics | Power PDN | No route | `pdn/`; no route |
| kerf-electronics | Motor drive | No route | `motordrive/`; no route |
| kerf-electronics | Gate drive | No route | `gatedrive/`; no route |
| kerf-electronics | LED driver | No route | `leddriver/`; no route |
| kerf-electronics | Battery / BMS | No route | `battery/`, `charger/`; no HTTP endpoint |
| kerf-electronics | Antenna design | No route | `antenna/`; no route |
| kerf-electronics | Thermal (PCB thermal) | No route | `thermal/`; no route |
| kerf-electronics | DRC (design-rule check) | **Wired** | `pcbDRC.js` frontend-only; no backend route needed |
| kerf-electronics | ERC (electrical rule check) | **Wired** | `erc.js` frontend-only |

---

## Silicon / EDA

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-api (new) | RTL synthesis (Yosys) | **Route exists, no UI** | `POST /api/silicon/synth` — shipped this sweep; degrades to pending if yosys absent |
| kerf-electronics | PCB schematic capture | **Wired** | tscircuit circuit runner; `circuitRunner.js` |
| kerf-electronics | PCB layout (tscircuit) | **Wired** | tscircuit layout engine; `circuitWorker.js` |
| (planned) | Place-and-route (OpenROAD) | No route | Not yet implemented |
| (planned) | Static timing analysis | No route | Not yet implemented |
| (planned) | Formal verification | No route | Not yet implemented |

---

## Fluid Dynamics / CFD

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / fluidpower | Hydraulic system analysis | No route | `fluidpower/`; LLM tools only |
| kerf-cad-core / pneumatics | Pneumatic circuit analysis | No route | `pneumatics/`; LLM tools only |
| kerf-cad-core / pumpsys | Pump system design | No route | `pumpsys/`; LLM tools only |
| kerf-cad-core / hvac | HVAC load calc | No route | `hvac/`; no route |
| kerf-cad-core / psychro | Psychrometrics | No route | `psychro/`; no route |
| kerf-cad-core / flowmeter | Flowmeter sizing | No route | `flowmeter/`; no route |
| kerf-cad-core / waterhammer | Water hammer (transient) | No route | `waterhammer/`; no route |
| kerf-cad-core / piping | Piping stress analysis | No route | `piping/`; no route |
| kerf-cad-core / vacuum | Vacuum system | No route | `vacuum/`; no route |
| (planned) | CFD (OpenFOAM) | No route | Not yet implemented |

---

## Thermal

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / heatxfer | Heat exchanger sizing | No route | `heatxfer/`; no route |
| kerf-cad-core / thermalcut | Thermal cutting process | No route | `thermalcut/`; no route |
| kerf-cad-core / refrigeration | Refrigeration cycle | No route | `refrigeration/`; no route |
| kerf-cad-core / boiler | Boiler design | No route | `boiler/`; no route |
| kerf-cad-core / thermocycle | Power cycle analysis | No route | `thermocycle/`; no route |
| kerf-cad-core / heattreat | Heat treatment spec | No route | `heattreat/`; no route |

---

## Mechanical / Machine Design

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / shaft | Shaft design + critical speed | No route | `shaft/`; LLM tools only |
| kerf-cad-core / bearings | Bearing selection + life | No route | `bearings/`; LLM tools only |
| kerf-cad-core / gearstrength | Gear strength (AGMA/ISO) | No route | `gearstrength/`; no route |
| kerf-cad-core / gearbox | Gearbox design | No route | `gearbox/`; no route |
| kerf-cad-core / beltchain | Belt/chain drive | No route | `beltchain/`; no route |
| kerf-cad-core / clutchbrake | Clutch/brake design | No route | `clutchbrake/`; no route |
| kerf-cad-core / springs | Spring design | No route | `springs/`; no route |
| kerf-cad-core / fasteners | Fastener selection | No route | `fasteners/`; LLM tools only |
| kerf-cad-core / vibration | Vibration analysis | No route | `vibration/`; no route |
| kerf-cad-core / dynamics | Multi-body dynamics | No route | `dynamics/`; no route |
| kerf-cad-core / kinematics | Kinematic linkages | No route | `kinematics/`; no route |
| kerf-cad-core / crane | Crane/lifting design | No route | `crane/`; no route |
| kerf-cad-core / conveyor | Conveyor design | No route | `conveyor/`; no route |

---

## CAD / Geometry

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core | OCCT B-rep kernel (Phase 2–3) | **Wired** | `occtWorker.js` + `occtRunner.js`; full Pad/Pocket/Fillet pipeline |
| kerf-cad-core | NURBS surfacing (Phase 4) | Partial | `surfacing.py`; frontend `subd.js`; NURBS long-tail |
| kerf-cad-core | Sketch solver (PlaneGCS) | **Wired** | `sketchSolver.js` + WASM; full constraint solving |
| kerf-cad-core | Sheet metal (bend table) | Partial | `sheet_metal.py`; no dedicated UI panel |
| kerf-cad-core | Thread features | No route | `feature_thread.py`; OCCT only |
| kerf-cad-core / nesting | 2D nesting (bin packing) | No route | `nesting/pack.py`; LLM tools only |
| kerf-cad-core / gdt | GD&T annotation | Partial | `drawings/` backend; `gdt_callouts/`; no dedicated UI panel |
| kerf-tess | STEP tessellation | **Wired** | `notify_step_uploaded`; worker pipeline |
| kerf-render | Path-tracing render | **Wired** | `heroShot.js` + `heroShotBrowserPT.js`; render dropdown |
| kerf-cam | CAM toolpath generation | **Wired** | `kerf-cam` plugin; `CAMView.jsx` + `LayeredCAMView` wired in Editor (2026-05-24) |
| kerf-slicing | FDM slicing (Cura) | **Wired** | `POST /run-print-slice`; `PrintSliceView.jsx` imported and rendered in Editor (2026-05-24) |
| kerf-imports | FreeCAD import | Route exists, no UI | `POST /import-freecad-project`; drag-and-drop import UI |
| kerf-imports | Rhino 3dm import | Route exists, no UI | `rhino3dm_route.py`; `rhino3dm.js` frontend |

---

## Civil / Infrastructure

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / civil | Road / earthworks design | No route | `civil/`, `earthworks/`; no route |
| kerf-cad-core / surveying | Coordinate geometry (COGO) | No route | `surveying/cogo.py`; LLM tools |
| kerf-cad-core / geotech | Geotechnical analysis | No route | `geotech/`; no route |
| kerf-cad-core / hydrology | Hydrology (storm water) | No route | `hydrology/`; no route |
| kerf-cad-core / spillway | Spillway hydraulics | No route | `spillway/`; no route |
| kerf-cad-core / pavement | Pavement design | No route | `pavement/`; no route |
| kerf-cad-core / railway | Railway track design | No route | `railway/`; no route |
| kerf-bim | BIM IFC | **Wired** | BIM plugin route; `BIMView.jsx` wired in Editor (2026-05-24) |
| kerf-cad-core / arch | Architectural elements | Partial | `curtainWall.js`, `railings.js`, `stairs.js` frontend; no route |
| kerf-cad-core / windload | Wind load analysis | No route | `windload/`; no route |
| kerf-cad-core / seismic | Seismic design | No route | `seismic/`; no route |
| kerf-cad-core / firesafety | Fire safety calculation | No route | `firesafety/`; no route |
| kerf-cad-core / buildingenergy | Building energy model | No route | `buildingenergy/`; no route |

---

## Wiring / Electrical (non-PCB)

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-wiring | WireViz harness diagram | **Wired** | `POST /run-wireviz`; `WiringView.jsx` wired in Editor (2026-05-24) |
| kerf-plc | PLC IEC-61131 lint | **Wired** | `POST /lint-plc`; `PLCView.jsx` imported and rendered in Editor (2026-05-24) |
| kerf-cad-core / elecpower | Power systems analysis | No route | `elecpower/`; no route |
| kerf-cad-core / harness | Harness routing | No route | `harness/`; no route |

---

## Marine / Naval

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / navalarch | Naval architecture (hydrostatics) | No route | `navalarch/hydrostatics.py`; no route |
| kerf-cad-core / marine | Marine structures | No route | `marine/`; no route |
| kerf-cad-core / mooring | Mooring analysis | No route | `mooring/`; no route |
| kerf-cad-core / hydroturbine | Hydro turbine design | No route | `hydroturbine/`; no route |

---

## Manufacturing / Process

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / cam_wizard | CAM wizard | No route | `cam_wizard/`; no route |
| kerf-cad-core / cuttingtool | Cutting tool database | No route | `cuttingtool/`; no route |
| kerf-cad-core / cncfeeds | CNC feeds & speeds | No route | `cncfeeds/`; no route |
| kerf-cad-core / fiveaxis | 5-axis toolpath | No route | `fiveaxis/`; no route |
| kerf-cad-core / turning | Turning operations | No route | `turning/`; no route |
| kerf-cad-core / injection | Injection moulding | No route | `injection/`; no route |
| kerf-cad-core / forming | Metal forming | No route | `forming/`; no route |
| kerf-cad-core / casting | Casting design | No route | `casting/tools.py`; LLM tools only |
| kerf-cad-core / additive | Additive mfg (build orientation) | No route | `additive/`; no route |
| kerf-cad-core / dfm | DFM checks | Partial | `dfmOverlay.js` frontend; no backend DFM route |
| kerf-cad-core / cmm | CMM inspection plan | No route | `cmm/`; no route |

---

## Cost / Procurement

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-cad-core / costing | Cost estimation | No route | `costing/`; no route |
| kerf-cad-core / quoting | RFQ quoting | No route | `quoting/`; no route |
| kerf-parts | Parts + distributor search | **Wired** | Library/BOM distributor routes; `BOMTable.js` |
| kerf-pricing | Billing metering | **Wired** | Cloud billing routes; `BillingPanel.js` |

---

## Other / Cross-cutting

| Package | Capability | Frontend Status | Notes |
|---------|-----------|-----------------|-------|
| kerf-topo | Topology optimisation | **Wired** | `/run-topo`; `TopoView.jsx` imported and rendered in Editor (2026-05-24) |
| kerf-cad-core / reliability | Reliability (FMEA, MTTF) | No route | `reliability/`; no route |
| kerf-cad-core / controls | Control system design | No route | `controls/`; no route |
| kerf-cad-core / robotics | Robotics kinematics | No route | `robotics/`; no route |
| kerf-cad-core / optics | Optical design | No route | `optics/`; no route |
| kerf-cad-core / photonics | Photonics | No route | Similar to electronics; no route |
| kerf-cad-core / acoustics | Acoustic analysis | No route | `acoustics/`; no route |
| kerf-cad-core / procsim | Process simulation | No route | `procsim/`; no route |
| kerf-cad-core / lubrication | Lubrication analysis | No route | `lubrication/`; no route |
| kerf-cad-core / corrosion | Corrosion / cathodic protection | No route | `corrosion/cp.py`; LLM tools |
| kerf-cad-core / welding | Welding procedure | Partial | `welding/`; `weldment.py`; no route |

---

## Summary — Gap count by area

| Area | Total capabilities | Wired | Route/No UI | No Route |
|------|--------------------|-------|-------------|----------|
| Aerodynamics / Atmos | 12 | 0 | 2 | 10 |
| Propulsion | 6 | 0 | 2 | 4 |
| Composites / Structures | 11 | 0 | 2 | 9 |
| Electronics / PCB | 14 | 6 | 2 | 6 |
| Silicon / EDA | 6 | 2 | 1 | 3 |
| Fluid / CFD | 10 | 0 | 0 | 10 |
| Thermal | 6 | 0 | 0 | 6 |
| Mechanical | 13 | 0 | 0 | 13 |
| CAD / Geometry | 13 | 7 | 4 | 2 |
| Civil / Infrastructure | 13 | 0 | 1 | 12 |
| Wiring / Electrical | 4 | 0 | 2 | 2 |
| Marine / Naval | 4 | 0 | 0 | 4 |
| Manufacturing / Process | 11 | 0 | 0 | 11 |
| Cost / Procurement | 4 | 2 | 0 | 2 |
| Other | 10 | 0 | 0 | 10 |
| **Total** | **137** | **17** | **16** | **104** |

**Highest-value unwired routes (next sweep recommendations):**
1. `POST /api/aero/atmosphere` → atmosphere panel in project sidebar (ISA data already live)
2. `POST /api/composites/clt` → CLT stacking sequence panel  
3. `POST /api/aero/propulsion/tsiolkovsky` → Δv budget widget in project panel
4. `POST /api/electronics/rf` → RF link budget panel (route exists, no frontend)
5. `POST /api/topo/run` → topology opt result viewer (Opus agent result → viewport)
