# Weld Distortion Estimator — `procsim/weld_distortion.py`

Residual stress and distortion prediction for weld passes using a 1-D
transient finite-difference thermal model (Goldak/Rosenthal heat source),
simplified thermal-elastic-plastic inherent-strain method (Ueda 1975),
Masubuchi transverse shrinkage, and Okerblom angular distortion cross-check.

All functions are pure Python. All return `{"ok": bool, ...}`; never raise.
Units are SI-compatible (mm for lengths, kJ/mm for heat input, MPa for stress).

---

## Physical model

1. **Transient thermal** — Rosenthal quasi-stationary 3-D point source evaluated
   at a through-thickness depth profile. 1-D FD time-stepping (explicit) for
   transient history at the weld centreline.
2. **Inherent strain** — simplified Ueda model:
   `ε_inh(z) ≈ α_exp · max(0, T_peak(z) − T_yield_drop)`.
3. **Angular distortion** from through-thickness strain gradient (FD/IS model);
   cross-checked against Okerblom empirical formula.
4. **Transverse shrinkage** from Masubuchi formula.
5. **Longitudinal shrinkage** from integrated strain.
6. **Buckling risk** — residual stress vs elastic plate buckling critical stress.
7. **Mitigation suggestions** based on distortion magnitude.

---

## Supported materials

`material` key: `"steel"`, `"aluminium"`, `"stainless_304"`.

---

## Public API

### `weld_distortion(t_mm, weld_length_mm, HI_kJ_mm, leg_mm=None, joint_type="bead_on_plate", material="steel", T_preheat_C=20.0, T_ambient_C=20.0, restrained=False, weld_speed_mm_s=5.0, eta=0.80, n_cells=20, n_thermal_steps=None) → dict`

Predict distortion and residual stress for a single weld pass.

**Key parameters:**

| Parameter | Notes |
|---|---|
| `t_mm` | Plate thickness [mm] |
| `weld_length_mm` | Weld run length [mm] |
| `HI_kJ_mm` | Arc heat input [kJ/mm] — must be > 0 |
| `leg_mm` | Fillet weld leg [mm]; required for `"fillet"` joint; defaults to `t_mm/2` |
| `joint_type` | `"bead_on_plate"`, `"fillet"`, or `"butt"` |
| `material` | Material key |
| `T_preheat_C` | Preheat / interpass temperature [°C] |
| `restrained` | True = fixture correction (reduces angular distortion, increases residual stress) |
| `weld_speed_mm_s` | Travel speed [mm/s] |
| `eta` | Process thermal efficiency (0–1]; 0.80 = SMAW default |
| `n_cells` | Through-thickness FD cells (default 20) |

Returns `{"ok": True, ...}` with:

```
theta_fd_rad, theta_fd_deg,
theta_okerblom_rad, theta_okerblom_deg,
transverse_shrinkage_mm,
longitudinal_shrinkage_mm,
inherent_strain_surface, inherent_strain_root,
residual_stress_centre_MPa, residual_stress_edge_MPa,
T_peak_surface_C, T_peak_root_C,
heat_input_kJ_mm, energy_total_J,
buckling_risk, sigma_cr_MPa,
mitigation_suggestions, warnings
```

### `weld_sequence_distortion(passes, material="steel", T_preheat_C=20.0) → dict`

Estimate total distortion for a multi-pass or multi-weld sequence.

Each element of `passes` is a parameter dict for `weld_distortion` (must contain
at minimum `t_mm`, `weld_length_mm`, `HI_kJ_mm`). Distortions accumulate
additively for unidirectional sequences.

Returns `{"ok", "total_theta_deg", "total_transverse_shrinkage_mm",
"total_longitudinal_shrinkage_mm", "total_energy_J", "pass_results",
"warnings", "mitigation_suggestions"}`.

---

## Usage

```python
from kerf_cad_core.procsim.weld_distortion import weld_distortion, weld_sequence_distortion

# Single MIG bead on 6 mm carbon steel plate
result = weld_distortion(
    t_mm=6.0,
    weld_length_mm=300.0,
    HI_kJ_mm=0.540,      # = power × time / length
    joint_type="bead_on_plate",
    material="steel",
    T_preheat_C=20.0,
    weld_speed_mm_s=8.0,
    eta=0.85,
)
print(f"angular distortion: {result['theta_fd_deg']:.2f}°")
print(f"transverse shrinkage: {result['transverse_shrinkage_mm']:.3f} mm")
print(f"buckling risk: {result['buckling_risk']}")

# Multi-pass sequence (e.g. two balanced weld runs)
passes = [
    {"t_mm": 6.0, "weld_length_mm": 300.0, "HI_kJ_mm": 0.540},
    {"t_mm": 6.0, "weld_length_mm": 300.0, "HI_kJ_mm": 0.540,
     "joint_type": "fillet"},
]
seq = weld_sequence_distortion(passes, material="steel")
print(f"total angular: {seq['total_theta_deg']:.2f}°")
```

---

## Notes

- `HI_kJ_mm` = (arc power [W] × efficiency η) / (travel speed [mm/s]) / 1000.
  E.g. 4000 W at η=0.80, 8 mm/s → HI = 4000×0.80/(8×1000) = 0.40 kJ/mm.
- `theta_fd_deg` (FD/inherent-strain model) is the primary result.
  `theta_okerblom_deg` is an empirical cross-check; expect ±20–30% difference.
- `restrained=True` increases residual stress by approximately 30% but reduces
  angular distortion; appropriate for heavily jigged fixtures.
- `n_cells` < 20 degrades thermal accuracy; increase to 40+ for thick plates
  (> 20 mm) or tight heat-input control.

## References

- Rosenthal, D. (1941). "Mathematical theory of heat distribution during welding
  and cutting." *Welding Journal* 20(5).
- Ueda, Y. et al. (1975). "A new measuring method of residual stresses with the
  aid of finite element method." *Trans. JWRI* 4(2).
- Masubuchi, K. (1980). *Analysis of Welded Structures.* Pergamon Press —
  transverse shrinkage formula.
- Okerblom, N.O. (1958). *The Calculations of Deformations of Welded Metal
  Structures.* HMSO London — empirical angular distortion.
