# procsim_solidification — Transient Casting Solidification Simulation

Explicit finite-difference transient heat-conduction solidification using the enthalpy method. 1-D and 2-D solvers for casting hot-spot analysis, solidification time, thermal modulus mapping, and cooling-curve extraction.

## When to use

Use these tools when an engineer needs to:
- Simulate solidification of a metal casting in 1-D or 2-D
- Identify hot spots (last-to-solidify regions) that risk porosity or shrinkage
- Compute the thermal modulus map (V/A) as a proxy for solidification sequence
- Extract cooling curves at specific probe locations within the casting
- Estimate solidification time using Chvorinov's rule without running a full simulation
- Look up thermo-physical properties (liquidus, solidus, latent heat, conductivity, density, cp) for a casting alloy

Keywords: solidification, casting simulation, enthalpy method, finite difference, latent heat, hot spot, solidification time, thermal modulus, cooling curve, Chvorinov, mushy zone, liquidus, solidus, mold interface, Robin boundary, CFL condition, casting alloy.

## Supported alloys

| Key | Description | T_liq (°C) | T_sol (°C) |
|---|---|---|---|
| `aluminium` (aliases: `al`, `aluminum`) | Aluminium casting alloy | 660 | 580 |
| `steel` (aliases: `carbon_steel`, `cast_steel`) | Carbon / cast steel | 1500 | 1400 |
| `bronze` (alias: `bronze_alloy`) | Bronze (Cu-Sn base) | 1000 | 880 |
| `za` (aliases: `za8`, `za12`) | ZA-8 / ZA-12 zinc-aluminium die-casting alloy | 404 | 375 |

## Physics / references

- **Enthalpy method**: Voller, V.R. & Prakash, C. (1987). Int. J. Heat Mass Transfer 30(8): 1709–1719
- **Solidification processing**: Flemings, M.C. (1974). "Solidification Processing." McGraw-Hill
- **Chvorinov's rule**: Chvorinov, N. (1940). Giesserei 27
- **Alloy data**: ASM Handbook Vol. 15: Casting. ASM International

Explicit Euler; stable when dt ≤ dx² / (2α) — CFL condition checked and returned as metadata.

Mold boundary: Robin condition with lumped heat-transfer coefficient `h_interface` [W·m⁻²·K⁻¹]; mold temperature `T_mold` held constant (infinite-mold assumption).

## Tools

| Tool | Description |
|------|-------------|
| `run_solidify_1d` | 1-D FD solidification; returns: `solidification_times_s` per cell, `hot_spot_index`, `thermal_modulus_map`, `cooling_curves` at probe positions; required: `length_m`, `n_cells`, `dt`, `n_steps`, `alloy` |
| `run_solidify_2d` | 2-D FD solidification on a rectangular domain; same outputs as 1-D plus 2-D solid-fraction field; required: `grid` `{nx, ny, dx, dy}`, `dt`, `n_steps`, `alloy` |
| `run_alloy_properties` | Read-only: return thermo-physical properties dict for a named alloy; required: `alloy` |

### Key inputs

**Shared:**
- `alloy` — alloy key (see table above)
- `T_pour` — pouring temperature (°C, must be > T_liq)
- `T_mold` — mold temperature (°C, must be < T_sol)
- `h_interface` — mold–casting heat transfer coefficient (W·m⁻²·K⁻¹); typical range 200–2000 for investment, 500–5000 for sand, 3000–20000 for die casting
- `probes` — list of probe positions (fraction of length for 1-D, or `{i, j}` cell indices for 2-D)
- `dt` — time step (s); must satisfy CFL: dt ≤ dx²/(2α)

**`run_solidify_1d` specific:**
- `length_m` — casting domain length (m)
- `n_cells` — number of 1-D cells (≥ 5)
- `n_steps` — number of time steps to run

**`run_solidify_2d` specific:**
- `grid` — `{nx: int, ny: int, dx: float, dy: float}` — cell counts and cell sizes (m)

### Outputs

- `ok` — bool; false if CFL violated or bad inputs
- `solidification_times_s` — per-cell time when solid fraction first reaches 1.0
- `hot_spot_index` — index of the last cell to solidify (highest porosity risk)
- `thermal_modulus_map` — V/A proxy per cell (higher = slower solidification)
- `cooling_curves` — `{position: [...], time_s: [...], T_C: [...], solid_frac: [...]}` per probe
- `cfl_status` — `{ok: bool, max_dt_allowed: float}`

### `run_alloy_properties` output fields

`T_liq`, `T_sol`, `L` (latent heat J/kg), `k` (W/m/K), `cp` (J/kg/K), `rho` (kg/m³)

## Example

Engineer: "Simulate 1-D solidification of a steel casting (0.1 m long, 50 cells) poured at 1540°C into a mold at 200°C."

1. `run_alloy_properties` — alloy=`steel` → k=35, cp=600, rho=7850; compute α = k/(ρ·cp) = 7.45e-6 m²/s; max_dt for 2 mm cells ≈ 0.27 s
2. `run_solidify_1d` — length_m=0.1, n_cells=50, dt=0.2, n_steps=2000, alloy=`steel`, T_pour=1540, T_mold=200, h_interface=800, probes=[0.1, 0.5, 0.9]
   → hot_spot_index=25 (centre), solidification_times_s, cooling_curves at three probe positions
