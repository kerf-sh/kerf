# Bulk Metal Forming

Pure-Python Hollomon / Siebel / Hosford-Caddell bulk metal forming calculations. No OCC dependency.
All tools are stateless — they compute and return results; no DB write. Units: SI (Pa, m, m², J).

---

## When to use

Forging, extrusion, rolling, wire drawing, flow stress, strain hardening, Hollomon equation,
open-die forging, closed-die forging, impression-die, flash, upset forging, forward extrusion,
backward extrusion, indirect extrusion, flat rolling, cold rolling, hot rolling, passes required,
forming work, adiabatic temperature rise, metal forming force, press tonnage, manufacturing.

---

## Tools

### `forming_flow_stress`

Hollomon power-law instantaneous flow stress: σ_f = K · ε^n.

**Input:** `K` (Pa, required), `eps` (true strain, required), `n` (strain-hardening exponent, required)

**Returns:** `sigma_f_Pa`

---

### `forming_mean_flow_stress`

Mean flow stress over strain range 0 → ε_f: σ̄_f = K · ε_f^n / (n + 1).

**Input:** `K` (Pa, required), `n` (required), `eps_f` (final true strain, required)

**Returns:** `sigma_f_mean_Pa`

---

### `forming_upset_forging_force`

Open-die upset forging force with Coulomb friction (Siebel slab method).
p_avg = σ_f · (1 + 2·μ·R_f / (3·h_f)).

**Input:** `sigma_f` (Pa, required), `A0` (m², required), `h0` (m, required), `hf` (m, required),
`mu` (default 0.1)

**Returns:** `F_N`, `F_MN`, `p_avg_Pa`, friction warnings

---

### `forming_closed_die_load`

Closed-die (impression-die) forging load: F = Kf · σ̄_f · A_proj.

**Input:** `sigma_f` (Pa, required), `A_proj` (m², required), `Kf` (default 6.0; range 3–9)

**Returns:** `F_N`, `F_MN`, `F_tonne_force`

---

### `forming_forward_extrusion`

Forward (direct) extrusion pressure and force. Modified Johnson/Altan upper-bound formula.

**Input:** `sigma_f` (Pa, required), `A0` (m², required), `Af` (m², required),
`mu` (default 0.05), `die_half_angle_deg` (default 45°), `L` (billet length, default 0)

**Returns:** `p_e_Pa`, `F_N`, `F_MN`, `R_extrusion`, `eps_extrusion`

---

### `forming_backward_extrusion`

Backward (indirect) extrusion pressure and force. p_e = σ̄_f · B · ln(R).
No container-wall friction.

**Input:** `sigma_f` (required), `A0` (required), `Af` (required),
`mu` (default 0.05), `die_half_angle_deg` (default 45°)

**Returns:** `p_e_Pa`, `F_N`, `F_MN`, `pressure_ratio_vs_forward`

---

### `forming_flat_rolling`

Flat rolling: contact length, roll force, torque, power, neutral point, max draft.

**Input:** `sigma_f` (required), `mu` (required), `R` (roll radius m, required),
`h0` (incoming thickness m, required), `hf` (outgoing thickness m, required),
`w` (strip width m, required), `omega_rad_s` (optional)

**Returns:** `L_c_m`, `F_N`, `T_Nm`, `P_W`, `delta_h_max_m`, warnings

---

### `forming_wire_drawing`

Wire/bar drawing stress, force, max reduction, limiting reduction (Hosford-Caddell).
B = μ·cot(α); σ_d = σ̄_f · (B/(B-1)) · [1 − (Af/A0)^((B-1)/B)].

**Input:** `sigma_f` (required), `A0` (required), `Af` (required),
`mu` (default 0.05), `die_half_angle_deg` (default 8°)

**Returns:** `sigma_d_Pa`, `F_N`, `r_max_per_pass`, `r_max_frictionless`, warnings

---

### `forming_work`

Forming work/energy and adiabatic temperature rise.
W = F · d / η; ΔT = W / (ρ · V · C_p).

**Input:** `F_N` (required), `displacement_m` (required), `eta` (default 1.0),
`rho` (default 7850), `Cp` (default 502), `volume_m3` (default 0)

**Returns:** `W_J`, `W_kJ`, `delta_T_C` (if volume given), warnings

---

### `forming_passes_required`

Minimum rolling/drawing passes for a total reduction.
n = ceil(ln(1 − r_total) / ln(1 − r_per_pass)).

**Input:** `r_total` (fractional, required), `r_per_pass` (fractional, required)

**Returns:** `n_passes`, `eps_per_pass`, `eps_total`, warnings (>20 passes → anneal)

---

## Example

```
1. forming_mean_flow_stress  K:530e6  n:0.26  eps_f:0.35
   → sigma_f_mean_Pa: 380e6

2. forming_closed_die_load  sigma_f:380e6  A_proj:0.015  Kf:6
   → F_MN: 34.2  F_tonne_force: 3490

3. forming_passes_required  r_total:0.75  r_per_pass:0.20
   → n_passes: 7  eps_total: 1.39
```
