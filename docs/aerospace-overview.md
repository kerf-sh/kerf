---
title: "Aerospace engineering in Kerf"
group: reference
order: 52
---

# Aerospace engineering in Kerf

The `kerf-aero` package extends Kerf with a full aerospace engineering workflow — from airfoil design and aerodynamic analysis through orbital mechanics, propulsion sizing, attitude-control design, thermal modelling, and 6-DOF flight simulation. Every sub-discipline is an installable subpackage, and each ships its own LLM tools so the assistant can drive the full pipeline from a natural-language description.

---

## Package overview

| Subpackage | Capability tag | What it covers |
|------------|---------------|----------------|
| `kerf-aero[airfoils]` | `aero.airfoils` | NACA/custom airfoil geometry, Xfoil polar analysis, lift/drag curves |
| `kerf-aero[orbital]` | `aero.orbital` | Keplerian propagation, TLE ingestion, Hohmann / bi-elliptic transfers, ground tracks |
| `kerf-aero[propulsion]` | `aero.propulsion` | Rocket engine sizing, nozzle geometry, Isp/thrust/burn-time trade studies |
| `kerf-aero[adcs]` | `aero.adcs` | Attitude Determination and Control — sensors, actuators, PID / LQR controllers |
| `kerf-aero[thermal]` | `aero.thermal` | Spacecraft thermal model — nodal network, orbit-average fluxes, hot/cold cases |
| `kerf-aero[flight_dynamics]` | `aero.flight_dynamics` | 6-DOF rigid-body simulation, trajectory integration, aero-database lookup |
| `kerf-aero[llm_tools]` | `aero.llm_tools` | LLM tool wiring for all sub-disciplines (auto-installed with any subpackage) |

Install a single subpackage or the full suite:

```bash
pip install "kerf-aero[airfoils]"          # just airfoils
pip install "kerf-aero[airfoils,orbital]"  # airfoils + orbital
pip install "kerf-aero"                    # all subpackages
```

---

## File types

| Extension | Kind | Editor / Viewer |
|-----------|------|-----------------|
| `.airfoil` | `airfoil` | Airfoil canvas — coordinate plot + polar overlay |
| `.polar` | `aero_polar` | Lift/drag/moment polar chart (Cl, Cd, Cm vs alpha) |
| `.orbit` | `orbital_state` | 3D orbit visualiser (three.js) |
| `.tle` | `tle_set` | Monaco (text), ingest via `orbital_ingest_tle` |
| `.trajectory` | `trajectory` | 3D path view — altitude, velocity, acceleration vs time |
| `.thruster` | `thruster_def` | Propulsion definition JSON |
| `.thermal_model` | `thermal_model` | Nodal network JSON + temperature timeline chart |
| `.adcs_config` | `adcs_config` | Attitude controller definition JSON |

---

## Workflow walkthrough

### 1. Airfoil design

Start with a NACA 4-series or 5-series airfoil, or define custom coordinates:

```
"Create a NACA 2412 airfoil and show me the polar at Re = 1e6."
```

`aero_create_airfoil` generates the coordinate set and writes a `.airfoil` file. `aero_run_polar` calls Xfoil (if installed) to compute Cl/Cd/Cm across an alpha sweep and writes the results to a `.polar` file. The polar is rendered as an interactive chart — click any alpha point to see the pressure distribution.

> **Xfoil is optional.** If Xfoil is not on `$PATH`, `aero_run_polar` falls back to the thin-airfoil analytic approximation (`Cl ≈ 2π sin α`) and marks the result as `"solver": "analytic"`.

**Typical Xfoil install:**
```bash
# Debian/Ubuntu
apt install xfoil
# macOS (Homebrew)
brew install xfoil
```

#### Comparing airfoils

```
"Compare the drag polars of NACA 0012 and NACA 2412 at Re = 500,000."
```

`aero_compare_polars` overlays two `.polar` files on the same chart.

---

### 2. Orbital mechanics

#### Two-line element (TLE) ingestion

```
"Import the ISS TLE and propagate the orbit for 24 hours."
```

`orbital_ingest_tle` parses a TLE string and writes an `.orbit` file. `orbital_propagate` integrates the orbit using SGP4 / J2 perturbations and appends a ground-track table.

#### Designing a transfer

```
"What is the delta-V for a Hohmann transfer from a 400 km circular orbit to a 35786 km GEO orbit?"
```

`orbital_hohmann_transfer` returns the two burn delta-Vs, time of flight, and a `.trajectory` file showing the transfer ellipse.

#### Ground track visualisation

```
"Show me the ground track for the next 12 passes over Cape Town."
```

`orbital_ground_track` projects the orbit onto a lat/lon map and marks pass windows and elevation angles.

---

### 3. Propulsion sizing

```
"Size a bipropellant engine for 500 N thrust at 300 s Isp using LOX/RP-1."
```

`propulsion_size_engine` runs the rocket equation and nozzle sizing trade, writes a `.thruster` file, and reports:
- Chamber pressure, area ratio, nozzle geometry
- Mass flow rate, burn time for a given propellant mass
- Estimated mass breakdown (combustion chamber, nozzle, valves)

```
"What is the delta-V of my CubeSat with a 0.5 kg thruster and 200 g of propellant?"
```

`propulsion_delta_v` applies the Tsiolkovsky rocket equation and returns total delta-V and burn time.

---

### 4. Attitude Determination and Control (ADCS)

```
"Design a nadir-pointing attitude controller for a 3U CubeSat with reaction wheels."
```

`adcs_design_controller` builds an LQR state-feedback controller for the given inertia tensor and actuator limits, writes an `.adcs_config` file, and returns settling time and steady-state pointing error estimates.

Sensor and actuator types supported:

| Type | Models |
|------|--------|
| Sensors | Star tracker, sun sensor, magnetometer, gyroscope, horizon sensor |
| Actuators | Reaction wheel, magnetorquer, thruster |
| Reference frames | LVLH, ECI, ECEF, body |

```
"Simulate the detumble manoeuvre from an initial tumble rate of 5 deg/s."
```

`adcs_simulate` integrates the rigid-body attitude equations with the controller and returns a time-series of quaternion attitude, angular rate, and actuator torque.

---

### 5. Thermal modelling

```
"Build a 5-node thermal model for a 3U CubeSat in a 550 km sun-synchronous orbit."
```

`thermal_build_model` constructs a nodal network JSON (`.thermal_model`) with:
- Solar, albedo, Earth-IR flux inputs from the orbit geometry
- Conductive and radiative couplings between nodes
- Hot case (maximum solar, maximum eclipse) and cold case scenarios

```
"What is the equilibrium temperature of the solar panel under worst-case illumination?"
```

`thermal_run_steady_state` solves the linear system and returns node temperatures. `thermal_run_transient` integrates through a full orbit period.

---

### 6. 6-DOF flight dynamics

```
"Simulate a 3-second burn of the main engine and show the resulting trajectory."
```

`flight_sim_run` integrates the 6-DOF equations of motion — forces (aero, thrust, gravity), moments (aero, control surfaces, reaction control) — and writes a `.trajectory` file.

The trajectory viewer shows altitude, velocity, Mach number, and angle of attack vs. time in an interactive chart. Click any timestamp to see the vehicle state in the 3D viewport.

---

## LLM tool summary

| Tool | Sector | Signature | Read/Write |
|------|--------|-----------|-----------|
| `aero_create_airfoil` | airfoils | `(naca, chord_m)` → `.airfoil` | write |
| `aero_run_polar` | airfoils | `(airfoil_path, re, alpha_range)` → `.polar` | write |
| `aero_compare_polars` | airfoils | `(polar_a, polar_b)` → chart overlay | read |
| `aero_read_polar` | airfoils | `(polar_path)` → JSON polar data | read |
| `orbital_ingest_tle` | orbital | `(tle_string)` → `.orbit` | write |
| `orbital_propagate` | orbital | `(orbit_path, duration_s)` → ground track | write |
| `orbital_hohmann_transfer` | orbital | `(r1_km, r2_km)` → delta-V, `.trajectory` | write |
| `orbital_ground_track` | orbital | `(orbit_path, duration_s, observer_lat, observer_lon)` → pass table | read |
| `propulsion_size_engine` | propulsion | `(thrust_N, isp_s, propellant)` → `.thruster` | write |
| `propulsion_delta_v` | propulsion | `(thruster_path, propellant_mass_kg, dry_mass_kg)` → delta-V | read |
| `adcs_design_controller` | adcs | `(inertia_tensor, actuator_type, mode)` → `.adcs_config` | write |
| `adcs_simulate` | adcs | `(adcs_config_path, initial_rate, duration_s)` → attitude time-series | write |
| `thermal_build_model` | thermal | `(orbit_path, node_defs)` → `.thermal_model` | write |
| `thermal_run_steady_state` | thermal | `(thermal_model_path, case)` → node temperatures | read |
| `thermal_run_transient` | thermal | `(thermal_model_path, orbit_periods)` → temperature vs time | write |
| `flight_sim_run` | flight_dynamics | `(vehicle_def, initial_state, manoeuvres)` → `.trajectory` | write |

All tools are available through the chat assistant — describe the analysis in plain language.

---

## Example prompts

```
"Create a NACA 2415 airfoil and compute drag polars from -5° to 20° at Re = 2e6."
"Given the attached TLE, how many times does the satellite pass over Johannesburg today?"
"Size a cold-gas thruster for 50 mN thrust using nitrogen at 300 bar."
"Build a thermal model for a 1U CubeSat and find the worst-case hot temperature."
"Simulate 30 seconds of flight after a pitch-up manoeuvre at Mach 0.8."
```

---

## See also

- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — full index of all 12 aero LLM tools
- [file-types.md](./file-types.md) — extension registry including aero file types
- [silicon-overview.md](./silicon-overview.md) — chip design workflows
- [capabilities.md](./capabilities.md) — capability tags and install personas
