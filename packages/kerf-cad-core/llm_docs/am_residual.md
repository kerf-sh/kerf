# Additive Manufacturing Residual Stress — `procsim/am_residual.py`

Inherent-strain-based residual stress and distortion estimates for LPBF
(laser powder bed fusion) and DED (directed energy deposition) processes.
Layer-by-layer 1-D Stoney/Euler-Bernoulli model; multi-orientation scan;
Arrhenius stress-relief soak.

All functions are pure Python (no NumPy). All return `{"ok": bool, ...}`;
never raise.

---

## Physical model

Each deposited layer contracts by `ε_inh = α_exp · (T_melt − T_ambient)`.
Elastic misfit stress in the new layer:
```
σ_layer = E · ε_inh / (1 − ν)   (biaxial, plane-stress)
```

Accumulated Stoney curvature at layer k:
```
κ_k = Σ_{i=1..k} σ_i · t_layer / (E · H_k² / 6)
```

Tip deflection (warpage): `δ = κ_N · L² / 2` (N = total layers).

Stress relief: Arrhenius relaxation `σ(t) = σ₀ · exp(−A · exp(−Q/(R·T)) · t)`.

Recoater collision risk is flagged when cumulative curl exceeds one layer
thickness.

---

## Supported materials

`material` key (case-insensitive): `"316l"`, `"ti64"`, `"alsi10mg"`, `"in625"`,
`"maraging"`. Each preset carries `E`, `nu`, `alpha`, `rho`, `T_melt`, `sy`,
`sr_A` (Arrhenius pre-exponential), `sr_Q` (activation energy).

---

## Public API

### `material_props(name) → dict`

Return thermo-mechanical properties for an AM material.

Returns `{"ok": True, "E", "nu", "alpha", "rho", "T_melt", "sy", "sr_A", "sr_Q", "name"}`.

### `stress_relief_soak(sigma_0, T_soak_C, t_soak_s, material="316l") → dict`

Arrhenius-type exponential stress relaxation during a post-build soak.

Parameters: `sigma_0` initial residual stress [Pa], `T_soak_C` soak temperature
[°C], `t_soak_s` soak duration [s].

Returns `{"ok", "sigma_0_Pa", "sigma_final_Pa", "fraction_remaining",
"relaxation_rate_per_s", "T_soak_C", "t_soak_s", "material"}`.

### `am_residual_1d(n_layers, layer_thickness, part_length, part_width, material="316l", process="lpbf", T_ambient=25.0, T_preheat=80.0, overhang_fraction=0.0, scan_rotation_deg=67.0) → dict`

Layer-by-layer 1-D inherent-strain accumulation along the build axis.

**Parameters:**

| Parameter | Units | Notes |
|---|---|---|
| `n_layers` | — | Number of deposited layers (int, > 0) |
| `layer_thickness` | m | Layer thickness |
| `part_length` | m | Part dimension along x |
| `part_width` | m | Part dimension along y |
| `material` | str | Material key |
| `process` | str | `"lpbf"` or `"ded"` |
| `T_ambient` | °C | Ambient / build-chamber temperature |
| `T_preheat` | °C | Build-plate pre-heat temperature |
| `overhang_fraction` | — | Fraction of layers with unsupported overhang (0–1) |
| `scan_rotation_deg` | deg | Layer-to-layer scan rotation (67° default = island) |

Returns `{"ok", "max_curvature_1_per_m", "tip_deflection_m",
"max_residual_stress_Pa", "avg_residual_stress_Pa", "recoater_collision_risk",
"per_layer": [{"layer", "sigma_Pa", "kappa_1_per_m", "deflection_m"}, ...],
"warnings"}`.

### `am_orient_scan(n_layers, layer_thickness, part_length, part_width, part_height, material, process, orientations) → dict`

Scan a list of build orientations (rotation angles [deg] about the longest axis)
and return the residual-stress metric for each; identify the minimum-residual
orientation.

Returns `{"ok", "results": [{"orientation_deg", "max_residual_stress_Pa",
"tip_deflection_m"}, ...], "best_orientation_deg", "best_max_stress_Pa",
"warnings"}`.

---

## Usage

```python
from kerf_cad_core.procsim.am_residual import (
    am_residual_1d, am_orient_scan, stress_relief_soak, material_props
)

# 400-layer Ti64 LPBF build
result = am_residual_1d(
    n_layers=400,
    layer_thickness=30e-6,   # 30 µm in metres
    part_length=0.05,        # 50 mm
    part_width=0.03,
    material="ti64",
    process="lpbf",
    T_preheat=100.0,
    scan_rotation_deg=67.0,
)
print(result["tip_deflection_m"] * 1000, "mm warpage")
print(result["recoater_collision_risk"])

# Find minimum-distortion orientation
scan = am_orient_scan(
    n_layers=400, layer_thickness=30e-6,
    part_length=0.05, part_width=0.03, part_height=0.012,
    material="ti64", process="lpbf",
    orientations=[0, 45, 90, 135],
)
print("best orientation:", scan["best_orientation_deg"], "deg")

# Stress relief soak
relief = stress_relief_soak(
    sigma_0=350e6, T_soak_C=600, t_soak_s=7200, material="316l"
)
print(f"stress remaining: {relief['fraction_remaining']*100:.0f}%")
```

---

## References

- Mercelis, P. & Kruth, J.-P. (2006). "Residual stresses in selective laser
  sintering and selective laser melting." *Rapid Prototyping Journal* 12(5).
- Stoney, G.G. (1909). "The tension of metallic films deposited by electrolysis."
  *Proc. R. Soc. A* 82(553) — curvature formula.
- Goldak, J. et al. (1984). "A new finite element model for welding heat sources."
  *Metallurgical Transactions B* 15(2) — thermal model reference.
