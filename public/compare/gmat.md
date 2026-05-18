---
slug: gmat
competitor: NASA GMAT
category: cad-sim
left: kerf
right: gmat
hero_tagline: "GMAT plans the mission — Kerf designs the spacecraft hardware that executes it."
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
| Orbit determination | Yes (via GMAT) | Yes (batch + sequential) |
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
