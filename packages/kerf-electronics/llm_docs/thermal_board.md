# Board-Level Thermal Map (`thermal_board`)

2D steady-state finite-difference thermal solver for PCB hotspot identification, per-component junction temperature, and copper/via recommendations.

---

## When to use

- Find the PCB hotspot under realistic power dissipation
- Calculate junction temperature Tj = T_board + P × θ_jc for each component
- Flag components that exceed their rated Tj_max
- Determine whether adding copper fill or thermal vias brings ΔT below a target

---

## Physics model

- **In-plane conduction:** `k_eff = f_cu × 390 + (1 − f_cu) × 0.3` W/(m·°C), where f_cu is the copper coverage fraction [0, 1].
- **Boundary:** convection + linearised radiation from both board surfaces. Natural convection default h = 10 W/(m²·°C). Forced convection via Pohlhausen flat-plate correlation (`Nu = 0.664 Re^0.5 Pr^(1/3)`) when `airflow_m_per_s > 0`.
- **Thermal vias:** modelled as additional vertical conductance to a cold backside node: `G_via = n × k_Cu × π r² / t_board`.
- **Solver:** Gauss–Seidel iteration, initialised at the global energy-balance mean temperature (dramatically improves convergence for high-k boards). Convergence criterion: max ΔT < `tol_k` (default 1e-4 °C).
- **Energy balance:** output includes `energy_balance_err = |P_in − P_out| / P_in`; should be ≪ 0.01 for a well-converged solve.

---

## LLM tools

### `board_thermal_map`

Solves the 2D temperature field and returns hotspot + per-component Tj.

**Required input:**
```json
{
  "width_m": 0.1,
  "height_m": 0.08,
  "components": [
    {"ref": "U1", "x_m": 0.05, "y_m": 0.04, "power_w": 3.0,
     "theta_jc": 2.5, "tj_max_c": 125}
  ]
}
```

**Optional fields:**
- `copper_coverage` (default 0.3), `copper_coverage_map` (ny×nx array)
- `ambient_c` (default 25), `h_conv` (default 10 W/(m²·°C)), `epsilon` (default 0.9)
- `airflow_m_per_s` + `board_length_m` — enable forced-convection h
- `t_board_m` (default 0.0016 m = 1.6 mm), `nx`/`ny` (default 20×20)
- `thermal_vias`: list of `{x_m, y_m, n_vias, r_via_m}`

**Returns** (T_field omitted from LLM payload — too large):
```json
{
  "peak_T_c": 74.3,
  "peak_ij": [9, 9],
  "components": [
    {"ref": "U1", "power_w": 3.0, "T_board_c": 66.8, "Tj_c": 74.3,
     "over_limit": false, "tj_max_c": 125, "margin_c": 50.7}
  ],
  "total_power_w": 3.0,
  "total_conv_rad_w": 2.998,
  "energy_balance_err": 0.0007
}
```

### `board_thermal_recommend`

Sweeps copper coverage and thermal-via counts at the hotspot to find the minimum change needed to meet a ΔT target.

**Input:**
```json
{
  "board": { /* same schema as board_thermal_map */ },
  "target_delta_t_c": 40.0,
  "n_via_options": [4, 8, 16, 32]
}
```

**Returns:**
```json
{
  "already_ok": false,
  "baseline_delta_t_c": 49.3,
  "target_delta_t_c": 40.0,
  "copper_recommendation": {
    "min_coverage": 0.65, "delta_t_c": 38.7,
    "note": "Increase copper coverage to 0.65"
  },
  "via_options": [
    {"n_vias": 4,  "delta_t_c": 44.1},
    {"n_vias": 8,  "delta_t_c": 39.2},
    {"n_vias": 16, "delta_t_c": 35.5},
    {"n_vias": 32, "delta_t_c": 32.0}
  ]
}
```

---

## Direct Python API

```python
from kerf_electronics.thermal_board import (
    BoardThermalMapInput, BoardComponent, ThermalVia,
    solve_board_thermal_map, recommend_copper_and_vias,
)

inp = BoardThermalMapInput(
    width_m=0.1, height_m=0.08,
    copper_coverage=0.3,
    components=[
        BoardComponent(ref="U1", x_m=0.05, y_m=0.04,
                       power_w=3.0, theta_jc=2.5, tj_max_c=125),
    ],
    ambient_c=25.0,
)
result = solve_board_thermal_map(inp)
print(result["peak_T_c"])   # °C
print(result["components"][0]["Tj_c"])

# Recommendation
rec = recommend_copper_and_vias(inp, target_delta_t_c=40.0)
print(rec["copper_recommendation"])
```

---

## Notes and limitations

- The model is 2D in-plane; it does not resolve through-thickness gradients or stacked vias.
- Component power is distributed uniformly to the nearest grid cell (point source approximation); use finer nx/ny (e.g. 40×40) for better spatial resolution.
- Vias are modelled as additional surface conductance, not as discrete 3D conductors.
- Gauss–Seidel convergence may be slow for very fine grids (nx/ny > 60) — increase `max_iter` if needed.
- References: Incropera §7.2 (flat-plate forced convection), IPC-2152 (copper current/thermal).
