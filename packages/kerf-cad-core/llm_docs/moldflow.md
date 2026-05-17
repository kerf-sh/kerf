# Injection Mould Flow Simulation — `procsim/moldflow.py`

1-D / 2.5-D injection-moulding fill simulation for a plate/strip cavity fed
from one or more gates. Power-law slit-flow rheology (Throne 1979); Carslaw-Jaeger
slab cooling (Rosato 2000).

All functions are pure Python (no NumPy). All return `{"ok": bool, ...}`;
never raise. Units are SI throughout (metres, Pascals, seconds).

---

## Physical model

**Rheology:** power-law `η_app = K · γ̇^(n-1)`.  
**Slit-flow pressure drop (Throne compact form):**  
`ΔP = 2K·L/h^(n+2) · ((2n+1)/n · Q/(2W))^n`  
For Newtonian (n=1): `ΔP = 6ηQL/(Wh³)` (standard H-P).

**Cooling (Carslaw-Jaeger first-term, symmetric slab):**  
`t_cool = t_wall²/(π²α) · ln((4/π) · (T_melt−T_mould)/(T_eject−T_mould))`

**Weld lines:** equidistant between adjacent gate pairs; hole obstacles
contribute one weld line at midpoint + hole_radius downstream.

**Sink-mark risk (Rosato rule):** `rib_wall_ratio > 0.6`.

---

## Built-in polymer presets

`material` key (case-insensitive): `"abs"`, `"pp"`, `"pe"`, `"ps"`, `"nylon66"`, `"pc"`.

Each preset carries: `K` [Pa·s^n], `n`, `rho` [kg/m³], `cp` [J/(kg·K)],
`k_melt` [W/(m·K)], `T_melt` [°C], `T_eject` [°C], `tau_limit` [Pa],
`shear_rate_limit` [s⁻¹].

---

## Public API

### `moldflow_fill(flow_length_m, t_wall_m, width_m, flow_rate_m3s, material="abs", n_gates=1, n_holes=0, hole_diameter_m=0.005, t_mould_C=60.0, rib_wall_ratio=0.0, n_cavities=1, runner_balanced=True) → dict`

Full 1-D / 2.5-D fill simulation. The main entry point.

**Key parameters:**

| Parameter | Units | Notes |
|---|---|---|
| `flow_length_m` | m | Cavity flow length — must be > 0 |
| `t_wall_m` | m | Nominal wall thickness (half-gap = t/2) |
| `width_m` | m | Cavity width |
| `flow_rate_m3s` | m³/s | Volumetric injection flow rate |
| `material` | str | One of the built-in polymer keys |
| `n_gates` | int | Equally-spaced gates along cavity (default 1) |
| `n_holes` | int | Circular holes (flow obstacles) for weld-line positioning |
| `t_mould_C` | °C | Mould surface temperature |
| `rib_wall_ratio` | — | `t_rib / t_wall` (0 = no rib) |
| `n_cavities` | int | Number of identical cavities |
| `runner_balanced` | bool | True = H-tree balanced; False = sequential manifold |

Returns `{"ok": True, ...}` with:

```
fill_time_s, pressure_drop_Pa, clamp_force_N, clamp_tonnage_t,
shear_rate_apparent_s⁻¹, shear_rate_true_s⁻¹, shear_stress_Pa,
shear_rate_over_limit, shear_stress_over_limit,
short_shot, frozen_layer_m,
weld_line_positions_m,
sink_mark_risk,
gate_diameter_m, runner_diameter_m,
cavity_fill_times_s, runner_balanced_equal,
cooling_time_s, thermal_diffusivity_m2s,
warnings
```

### `cooling_time(t_wall_m, material="abs", T_melt_C=None, T_mould_C=60.0, T_eject_C=None) → dict`

Stand-alone cooling time. Uses material preset temperatures unless overridden.

Returns `{"ok": True, "cooling_time_s", "thermal_diffusivity_m2s", "C_cool"}`.

### `pressure_drop_scan(flow_lengths_m, t_wall_m, width_m, flow_rate_m3s, material="abs") → dict`

Parametric sweep: compute `ΔP` for a list of flow lengths. Returns
`{"ok": True, "pressure_drops_Pa": [float, ...]}`. Useful for cross-checking
`ΔP ∝ L` scaling.

---

## Usage

```python
from kerf_cad_core.procsim.moldflow import moldflow_fill, cooling_time

# 150 mm × 80 mm × 3 mm cavity, PP, single gate
result = moldflow_fill(
    flow_length_m=0.150,
    t_wall_m=0.003,
    width_m=0.080,
    flow_rate_m3s=4e-6,   # 4 cm³/s
    material="pp",
    n_gates=1,
    t_mould_C=40.0,
)
print(result["fill_time_s"])          # fill time in seconds
print(result["clamp_tonnage_t"])      # clamp force in metric tonnes
print(result["weld_line_positions_m"]) # weld-line x-positions along cavity
print(result["short_shot"])           # True if freeze-off before fill completes

# Cooling only
ct = cooling_time(t_wall_m=0.003, material="pp", T_mould_C=40.0)
print(ct["cooling_time_s"])
```

---

## Notes

- All dimensions must be in SI (metres, m³/s, Pa). Millimetre inputs will give
  physically wrong results without explicit unit conversion.
- `short_shot` is flagged when the frozen layer thickness ≥ half-gap at the end
  of fill. Reduce wall thickness or increase flow rate to avoid it.
- Multi-cavity runner: `runner_balanced=True` → all cavities fill simultaneously
  (equal times). `runner_balanced=False` → sequential manifold → unequal fill times.
- `pressure_drop_scan` is a utility for verifying the `ΔP ∝ L` and `ΔP ∝ h^{-(n+2)}`
  scaling relationships in tests.

## References

- Throne, J.L. (1979). *Plastics Process Engineering.* Marcel Dekker — power-law
  slit flow.
- Rosato, D.V. & Rosato, M.G. (2000). *Injection Molding Handbook*, 3rd ed.
  Kluwer — sink-mark rule, gate sizing.
- Tadmor, Z. & Gogos, C.G. (2006). *Principles of Polymer Processing*, 2nd ed.
  Wiley — Rabinowitsch correction.
- Carslaw, H.S. & Jaeger, J.C. (1959). *Conduction of Heat in Solids*, 2nd ed.
  OUP — cooling time slab model.
- Brydson, J.A. (1995). *Plastics Materials*, 6th ed. Butterworth-Heinemann —
  gate/runner empirical sizing.
