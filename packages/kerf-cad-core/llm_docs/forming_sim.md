# Sheet Metal Forming Simulation — `procsim/forming_sim.py`

Sheet metal formability assessment using the Keeler-Goodwin Forming Limit Curve
(FLC), strain path analysis, safety margin, thinning, wrinkling tendency,
draw-bead / blank-holder force, limiting draw ratio, springback, and one-step
inverse strain estimation.

All functions are pure Python (no NumPy/SciPy). All return `{"ok": bool, ...}`;
never raise. Units are SI throughout (m for lengths, Pa for stress, dimensionless
for strains).

---

## Supported-input contract

Narrow by design:

- `flc0` / `flc_curve`: strain-hardening exponent `n > 0`, thickness `t` in
  metres (converted internally to mm for the Keeler-Goodwin formula). Validity
  range: `n` 0.10–0.60 typical; `t` up to ~6 mm (Keeler-Goodwin is empirical
  for deep-draw sheet, not thick plate).
- `safety_margin`: takes raw `(ε1, ε2)` strains plus the full FLC from
  `flc_curve`; reports three zones: `"safe"`, `"marginal"`, `"fail"`.
- `springback`: pure-bending (elastic) estimate only; no sidewall curl FE.
- `one_step_inverse`: section-based 2-D profile; 3-D parts require a full FE solver.

---

## Public API

### `flc0(n, t) → dict`

Keeler-Goodwin plane-strain intercept FLC₀:

```
FLC₀ (%) = (23.3 + 14.13·t_mm) × n / 0.21
```

Returns `{"ok", "n", "t_m", "t_mm", "FLC0_pct", "FLC0", "warnings"}`.

### `flc_curve(n, t, n_points=21) → dict`

Full FLC as `n_points` `(ε₂, ε₁_flc)` pairs on `[−FLC₀, +FLC₀]`.
Left half (draw side, ε₂ < 0): `ε₁_flc = FLC₀ − ε₂`.
Right half (stretch side, ε₂ > 0): `ε₁_flc = FLC₀ + 0.5·ε₂` (Goodwin approx).

Returns `{"ok", "n", "t_m", "FLC0", "curve": [{"eps2", "eps1_flc"}, ...],
"minimum_eps1", "plane_strain_eps2", "warnings"}`.

### `strain_path(mode, eps1_target, r_aniso) → dict`

Major/minor strain path for `mode` = `"deep_draw"`, `"stretch"`, or
`"plane_strain"`. Returns `{"ok", "eps1", "eps2", "mode", "description"}`.

### `safety_margin(eps1, eps2, n, t) → dict`

Distance of `(ε1, ε2)` from the FLC; zone classification.

Returns `{"ok", "zone": "safe"|"marginal"|"fail", "distance_to_flc",
"margin_fraction", "FLC0", "warnings"}`.

### `thinning(eps1, eps2) → dict`

Through-thickness thinning from volume conservation: `ε₃ = −ε₁ − ε₂`.

Returns `{"ok", "eps3", "thinning_pct"}`.

### `wrinkling_tendency(eps1, eps2, r_aniso, t, R_die) → dict`

Heuristic wrinkling index for the flange/wall region (Marciniak heuristic).

Returns `{"ok", "wrinkling_index", "risk": "low"|"medium"|"high", "warnings"}`.

### `draw_bead_restraining_force(t, sigma_y, mu, R_bead, w_bead) → dict`

Draw-bead restraining force per unit width (Stoughton 1988 model).

Parameters: `t` thickness [m], `sigma_y` yield stress [Pa], `mu` friction
coefficient, `R_bead` bead radius [m], `w_bead` bead width [m].

Returns `{"ok", "F_restraining_N_per_m", "warnings"}`.

### `blank_holder_force_window(sigma_y, t, A_blank, A_punch, mu, R_die) → dict`

Blank-holder force window `[F_min, F_max]` for wrinkle-free draw without fracture.

Returns `{"ok", "F_min_N", "F_max_N", "recommended_N", "warnings"}`.

### `limiting_draw_ratio(r_aniso, n) → dict`

Limiting draw ratio (LDR) from the Swift–Hill analytic formula.

Returns `{"ok", "LDR", "r_aniso", "n", "warnings"}`.

### `springback(sigma_y, E, t, R_punch, nu) → dict`

Springback for a pure-bend:
```
Rf/R = 1 − 3(σ_y/E)(2R/t) + 4(σ_y/E)³(2R/t)³   (Swift/Hosford)
```

Returns `{"ok", "R_punch_m", "R_final_m", "springback_ratio_Rf_R",
"springback_angle_correction_rad", "warnings"}`.

### `one_step_inverse(profile_coords, t, sigma_y, n, K) → dict`

Section-based one-step inverse strain estimate from a target 2-D part profile.

`profile_coords`: list of `(x, y)` points in metres.

Returns `{"ok", "max_strain", "avg_strain",
"strain_at_each_segment": [float, ...], "thinning_pct_max", "warnings"}`.

---

## Usage

```python
from kerf_cad_core.procsim.forming_sim import (
    flc0, flc_curve, safety_margin, springback
)

# Plane-strain intercept for DC04-like steel
r = flc0(n=0.21, t=0.0015)   # t in metres (1.5 mm)
print(r["FLC0_pct"])          # ~29.5%

# Full FLC
fld = flc_curve(n=0.21, t=0.0015, n_points=31)
pts = [(p["eps2"], p["eps1_flc"]) for p in fld["curve"]]

# Safety margin for a strain state
check = safety_margin(eps1=0.22, eps2=-0.05, n=0.21, t=0.0015)
print(check["zone"])   # "safe" / "marginal" / "fail"

# Springback for 5 mm radius punch, 1.5 mm sheet, σ_y=280 MPa
sb = springback(sigma_y=280e6, E=210e9, t=0.0015, R_punch=0.005, nu=0.3)
print(sb["springback_ratio_Rf_R"])
```

---

## References

- Keeler, S.P. (1965). "Determination of Forming Limits in Automotive Stampings."
  SAE Technical Paper 650535.
- Goodwin, G.M. (1968). "Application of Strain Analysis to Sheet Metal Forming
  Problems in the Press Shop." SAE Technical Paper 680093.
- Swift, H.W. (1952). "Plastic instability under plane stress." *J. Mech. Phys.
  Solids* 1(1): 1–18.
- Hill, R. (1952). "On discontinuous plastic states..." *J. Mech. Phys. Solids*
  1(1): 19–30.
- Stoughton, T.B. (1988). "Model of drawbead forces in sheet metal forming."
  Proc. 15th IDDRG Congress.
- Hosford, W.F. & Caddell, R.M. (2011). *Metal Forming: Mechanics and
  Metallurgy*, 4th ed. Cambridge University Press — §12.2 FLC.
- Marciniak, Z., Duncan, J.L. & Hu, S.J. (2002). *Mechanics of Sheet Metal
  Forming*, 2nd ed. Butterworth-Heinemann.
