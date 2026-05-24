---
slug: gmat
competitor: NASA GMAT
category: cad-sim
left: kerf
right: gmat
hero_tagline: "GMAT plans the mission — Kerf designs the spacecraft hardware that executes it."
reviewed_at: 2026-05-24
features:
  - domain: D5
    feature: "Lambert problem (multi-rev)"
    competitor:
      status: yes
      note: "GMAT built-in Lambert targeter (single- and multi-rev)"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273241"
    kerf:
      status: yes
      note: "Izzo 2015 multi-revolution"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/lambert.py"

  - domain: D5
    feature: "Orbital (Kepler, J2/J3, Hohmann)"
    competitor:
      status: yes
      note: "Keplerian, RK7/8, Adams-Bashforth-Moulton propagators"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273275"
    kerf:
      status: yes
      note: "Kepler + J2/J3 + Hohmann transfer"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/kepler.py"

  - domain: D5
    feature: "Perturbation force models (J2–J6, lunar/solar gravity)"
    competitor:
      status: yes
      note: "GGM02C Earth gravity, lunar/solar 3rd-body, point-mass ephemeris"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273281"
    kerf:
      status: yes
      note: "J2/J3/J4 + lunar/solar 3rd-body"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/perturbations.py"

  - domain: D5
    feature: "Atmospheric drag (NRLMSISE-00 / Jacchia-Roberts)"
    competitor:
      status: yes
      note: "NRLMSISE-00, Jacchia-Roberts, Exponential models; Cr/Cd configurable"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273281"
    kerf:
      status: yes
      note: "USSA76 + exponential drag; NRLMSISE not yet integrated"
      evidence: "packages/kerf-aero/src/kerf_aero/flight_dynamics/atmosphere.py"

  - domain: D5
    feature: "Solar radiation pressure (SRP)"
    competitor:
      status: yes
      note: "Dual-cone shadow + spherical SRP; Cr configurable"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273281"
    kerf:
      status: yes
      note: "SRP with cylindrical Earth shadow; Cr / area / mass configurable; in_shadow flag"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/perturbations.py"

  - domain: D5
    feature: "B-plane targeting"
    competitor:
      status: yes
      note: "BdotT/BdotR/C3 B-plane targeting sequences"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380274219"
    kerf:
      status: yes
      note: "B-plane frame (S/T/R triad), BdotT/BdotR from hyperbolic state, first-order ΔV differential correction"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/b_plane.py"

  - domain: D5
    feature: "Finite-burn manoeuvre modelling"
    competitor:
      status: yes
      note: "FiniteBurn object with thrust + Isp; integrated over arc"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273421"
    kerf:
      status: yes
      note: "Finite burn via Tsiolkovsky staging engine"
      evidence: "packages/kerf-aero/src/kerf_aero/propulsion/staging.py"

  - domain: D5
    feature: "Impulsive manoeuvre (delta-V)"
    competitor:
      status: yes
      note: "ImpulsiveBurn + Maneuver command; VNB and inertial frames"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273421"
    kerf:
      status: yes
      note: "Impulsive delta-V via Hohmann / transfers engine"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/transfers.py"

  - domain: D5
    feature: "Propulsion (Tsiolkovsky / staging / CEA thermochemistry)"
    competitor:
      status: partial
      note: "Chemical thruster model (Isp, thrust, tank); no CEA thermochemistry"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273421"
    kerf:
      status: yes
      note: "Tsiolkovsky + multi-stage + CEA-lite thermochemistry"
      evidence: "packages/kerf-aero/src/kerf_aero/propulsion/cea_lite.py"

  - domain: D5
    feature: "Orbit determination (batch least-squares + EKF)"
    competitor:
      status: yes
      note: "BatchEstimator + ExtendedKalmanFilter; range/Doppler/TDRSS obs types"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273617"
    kerf:
      status: partial
      note: "Batch weighted least-squares OD with STM measurement partials and formal covariance; range + range-rate observables; multi-station; J2 force model; a-priori constraint; EKF and real multi-pass tracking data ingestion (DSN/CCSDS TNF formats) not yet implemented"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/orbit_determination.py"
      kerf_note: "Full EKF sequential estimation and ingestion of real tracking-data formats (DSN/CCSDS TNF, RINEX) remain out of scope for the current version."

  - domain: D5
    feature: "Monte Carlo dispersion analysis"
    competitor:
      status: yes
      note: "Built-in Monte Carlo mission sequence with variable perturbation"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380274219"
    kerf:
      status: yes
      note: "Monte Carlo trajectory dispersion: wind/Cd/Cl/ignition-delay scatter; landing ellipse stats; p5/p50/p95 apogee/range"
      evidence: "packages/kerf-aero/src/kerf_aero/monte_carlo.py"

  - domain: D5
    feature: "State transition matrix (STM) propagation"
    competitor:
      status: yes
      note: "A-matrix + STM propagation for covariance and targeting"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273275"
    kerf:
      status: yes
      note: "Keplerian + J2 A-matrix; augmented RK4 STM (42-vector); P(t)=Φ P₀ Φᵀ covariance propagation; STM-based differential correction"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/stm.py"

  - domain: D5
    feature: "Launch window / access / coverage analysis"
    competitor:
      status: yes
      note: "ContactLocator, EclipseLocator, GroundStation access intervals"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380274213"
    kerf:
      status: yes
      note: "Ground station contact intervals (rise/set bisection, ECI→ECEF→ENU, min elevation mask); multi-station coverage metrics"
      evidence: "packages/kerf-aero/src/kerf_aero/orbital/coverage.py"

  - domain: D5
    feature: "Attitude dynamics (nadir / Sun-pointing / spin-stabilised)"
    competitor:
      status: yes
      note: "Spacecraft.Attitude: CoordinateSystemFixed, SpinStabilized, NadirPointing"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273305"
    kerf:
      status: yes
      note: "6-DOF attitude dynamics + stability derivatives"
      evidence: "packages/kerf-aero/src/kerf_aero/flight_dynamics/sixdof.py"

  - domain: D5
    feature: "Libration point orbit design"
    competitor:
      status: yes
      note: "CR3BP propagator; L1/L2/L4/L5 halo and Lissajous orbits"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273275"
    kerf:
      status: no
      note: "No CR3BP / libration point propagator"
      evidence: ""
      kerf_note: "Circular-restricted 3-body problem and halo orbit computation require dedicated differential corrector and continuation methods. This is large scope; not currently planned."

  - domain: D5
    feature: "Reentry / TPS analysis"
    competitor:
      status: yes
      note: "Entry Interface conditions, aerocapture sequences"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380273289"
    kerf:
      status: yes
      note: "Heat-flux trajectory + TPS stack sizing + ablation"
      evidence: "packages/kerf-aero/src/kerf_aero/reentry/heat_flux_trajectory.py"

  - domain: D5
    feature: "3D trajectory visualisation"
    competitor:
      status: yes
      note: "OpenGL OrbitView with solar system bodies, trajectory animation"
      source: "https://gmat.atlassian.net/wiki/spaces/GW/pages/380274197"
    kerf:
      status: no
      note: "General 3D viewport; no mission-specific trajectory animation"
      evidence: ""

  - domain: D5
    feature: "MATLAB / Python scripting API"
    competitor:
      status: yes
      note: "GMAT MATLAB interface + Python API (gmat.py); full object model exposed"
      source: "https://github.com/nasa/GMAT/blob/master/doc/help/src/UsingGmatApi.xml"
    kerf:
      status: yes
      note: "kerf-sdk on PyPI; JSON-RPC to all engines including aero/orbital"
      evidence: "packages/kerf-aero/src/kerf_aero/plugin.py"
---

# Kerf + NASA GMAT

NASA GMAT is not a competitor to Kerf. It is a complementary open-source orbital mechanics and mission analysis tool. Kerf integrates GMAT for spacecraft hardware projects — where GMAT's trajectory and mission analysis connects to the structural, propulsion, and avionics hardware designed in Kerf. This page explains what GMAT does, what Kerf adds, and why they are stronger together.

## What GMAT is

GMAT (General Mission Analysis Tool) is a high-fidelity space mission analysis and design tool developed by NASA Goddard Space Flight Center, with contributions from Thinking Systems Inc., the Korea Aerospace Research Institute, and others. It is open-source (Apache 2.0) and NASA's primary open-source tool for:

- **Trajectory design** — Keplerian propagation, Runge-Kutta integrators, Lambert targeting, B-plane targeting
- **Orbit determination** — batch least-squares, sequential estimation (EKF)
- **Manoeuvre planning** — impulsive and finite burns, targeting sequences
- **Launch window analysis** — access analysis, coverage analysis, ground contact scheduling
- **Attitude dynamics** — nadir-pointing, Sun-pointing, spin stabilised
- **Re-entry analysis** — aerocapture, entry interface conditions
- **Mission design for complex orbits** — libration point orbits, lunar orbits, interplanetary trajectories

GMAT has been used for real NASA missions including MAVEN, LADEE, Lunar Reconnaissance Orbiter support, and various Earth observation satellites. It runs on Windows, macOS, and Linux with a GUI and a MATLAB/Python scripting interface. It is Apache 2.0 licensed.

## Where they converge

Both GMAT and Kerf are open-source tools (GMAT: Apache 2.0; Kerf: MIT) used in aerospace engineering contexts without commercial licence costs. Both are used by small satellite teams, university CubeSat programs, and research institutions that cannot afford commercial tools (STK, MATLAB/Simulink). Both acknowledge that spacecraft design is multi-disciplinary — GMAT covers the mission and trajectory; Kerf covers the hardware that executes the mission.

## What Kerf adds

Kerf integrates GMAT as a companion tool for spacecraft hardware design projects:

- **Structural design of the spacecraft.** Design the chassis, primary structure, solar panel deployment mechanisms, and antenna mounts in Kerf's mechanical workspace with exact B-rep geometry. Structural FEM via CalculiX integration verifies load cases during launch. The structural model and the mission it flies are in the same Kerf project.
- **Avionics PCB design.** Design the on-board computer, power conditioning, attitude control electronics, RF subsystem, and payload interface boards in Kerf's PCB workspace. Pre-compliance simulate the RF antenna, power supply, and EMI containment — critical for a spacecraft where rework is impossible.
- **Chat-native mission analysis.** Describe a trajectory requirement — "design a transfer from LEO to a Sun-synchronous orbit at 500km with a 200m/s delta-V budget" — and the LLM invokes GMAT with the correct targeting sequences backed by GMAT documentation search.
- **Unified project.** GMAT script, trajectory data, structural CAD, avionics PCB, BOM, and mass budget are all in one Kerf project with cloud-git versioning — a complete spacecraft design record.
- **Mass budget from the CAD model.** Kerf's mechanical and PCB models carry material and component mass data; the mass budget is computed from the actual geometry, not estimated in a spreadsheet.

## Where GMAT is stronger on its own

- **Astrodynamics depth.** An experienced mission analyst using GMAT directly with hand-crafted scripts has access to the full mission design depth — custom integrators, complex multi-body targeting, STM propagation, Monte Carlo dispersion analysis — that Kerf's chat abstraction covers partially.
- **Validated mission heritage.** GMAT has flown on real NASA missions. Its trajectory propagators and manoeuvre targeting sequences have been verified against real navigation data. This heritage matters for mission-critical use.
- **MATLAB / Python GMAT API.** GMAT exposes a direct API for Monte Carlo, parametric sweep, and trade study automation. Kerf wraps this API through kerf-sdk; direct API users have finer control.
- **Visualisation.** GMAT's 3D solar system visualiser and trajectory animation are mission-analysis-specific and more capable than Kerf's general-purpose viewport for trajectory inspection.

## Feature matrix

| Feature | Kerf | NASA GMAT (standalone) |
|---|---|---|
| License | MIT (Kerf) + Apache 2.0 (GMAT) | Apache 2.0 |
| Trajectory design | Yes (via GMAT) | Yes (Keplerian, Lambert, B-plane) |
| Orbit determination | Partial (batch LS + covariance; EKF pending) | Yes (batch + sequential) |
| Manoeuvre planning | Yes (via GMAT) | Yes (impulsive + finite burn) |
| Launch window analysis | Yes (via GMAT) | Yes (access + coverage) |
| Re-entry analysis | Yes (via GMAT) | Yes |
| Interplanetary trajectories | Yes (via GMAT) | Yes |
| Chat-native mission design | Yes | No |
| Spacecraft structural CAD | In-box (Kerf mechanical) | Not included |
| Avionics PCB design | In-box (Kerf PCB + pre-compliance) | Not included |
| Structural FEM (launch loads) | Via CalculiX integration | Not included |
| Mass budget from CAD | Yes (from Kerf model) | Manual spreadsheet |
| Project version control | Cloud git (Kerf) | External (git manually) |
| Python scripting | kerf-sdk on PyPI | GMAT Python API |
| MATLAB interface | Not directly | Yes (GMAT MATLAB API) |
| 3D trajectory visualiser | Basic (Kerf viewport) | GMAT OpenGL visualiser |
| Mission heritage | N/A (integration layer) | MAVEN, LADEE, LRO support |
| Open source | Yes (MIT + Apache) | Yes (Apache 2.0) |

## Both produce CCSDS-compatible trajectory data

GMAT and Kerf's GMAT integration both produce trajectory data in standard formats: CCSDS OEM (Orbit Ephemeris Message) and GMAT's native report file format (CSV). Trajectory data produced via Kerf's chat interface is identical to data produced by a direct GMAT script run — standard CCSDS, consumable by any mission operations centre or navigation tool.

---
*Last reviewed: 2026-05-19. GMAT information sourced from gmat.gsfc.nasa.gov and the GMAT GitHub (gmatcentral.org). Kerf capabilities reflect the current shipped product.*
