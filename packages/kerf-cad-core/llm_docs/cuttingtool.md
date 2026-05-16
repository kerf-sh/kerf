# Cutting Tool Geometry and Machinability

Pure-Python machining and cutting-tool analysis: angle transforms, Merchant orthogonal cutting model, specific energy, Taylor tool-life equations, economic and maximum-production-rate cutting speeds, machinability rating, and nose-radius surface finish. No OCC dependency. All tools are stateless and never raise. References: Boothroyd & Knight (3rd ed.), Shaw (2nd ed.), Merchant (1945), Taylor (1907).

---

## When to use

Use these tools for metal-cutting analysis: tool rake and clearance angle conversion between orthogonal and normal planes, Merchant shear-angle and cutting-force model, specific cutting energy, material removal rate, Taylor VT^n = C tool-life prediction, extended Taylor tool life with feed and depth effects, economic cutting speed, maximum production rate speed, break-even speed analysis, machinability rating, theoretical surface finish Ra and Rt from nose radius and feed.

---

## Tools

### `cutting_tool_angle_transform`

Convert tool angles between orthogonal-plane and normal-plane systems, including inclination angle (3D oblique cutting). Directions: `orthogonal_to_normal` (default) or `normal_to_orthogonal`.

**Input:** `rake_deg`, `clearance_deg` (required); `direction`, `inclination_deg` (optional, default 0). **Returns:** output rake and clearance in target system.

---

### `cutting_tool_merchant`

Merchant minimum-energy orthogonal cutting model: shear angle φ = 45 + γ_o/2 − β/2, chip-thickness ratio, cutting force Fc, thrust force Ft, shear/friction/normal forces, chip and shear velocities.

**Input:** `gamma_o_deg` (rake), `tau_s_Pa` (shear strength ≈ 0.577×yield), `mu` (friction coeff), `t1_mm` (uncut chip thickness), `vc_m_min` (cutting speed) — all required; `width_b_mm` (optional, default 1.0). **Returns:** `phi_deg`, `r_c`, `t2_mm`, `Fc_N`, `Ft_N`, `shear_force_N`, `friction_force_N`, `chip_velocity_m_min`, `power_W`.

---

### `cutting_tool_specific_energy`

Specific cutting energy u = Fc/(b·t1) × 0.06 [J/mm³] and power P = Fc·vc/60 [W] and MRR [mm³/min].

**Input:** `Fc_N`, `b_mm` (width of cut), `t1_mm` (feed), `vc_m_min` — all required. **Returns:** `u_J_mm3`, `P_W`, `MRR_mm3_min`.

---

### `cutting_tool_taylor_life`

Taylor tool-life equation: T = (C/V)^(1/n) [min].

**Input:** `V_m_min`, `C_m_min` (Taylor constant), `n` (exponent, typically 0.1–0.5) — required; `VB_actual_mm`, `VB_reference_mm` (optional for wear-criterion correction). **Returns:** `T_min`, `warn_range`.

---

### `cutting_tool_taylor_extended_life`

Extended Taylor: V·T^n·f^a_f·d^a_d = C — accounts for feed and depth-of-cut effects.

**Input:** `V_m_min`, `C_m_min`, `n`, `f_mm_rev`, `a_f`, `d_mm`, `a_d` — all required; `f_ref_mm_rev`, `d_ref_mm` (optional, defaults 1.0). **Returns:** `T_min`, `C_eff_m_min`.

---

### `cutting_tool_economic_speed`

Economic (minimum cost per component) cutting speed: T_e = (1/n − 1)·(t_ct + C_tool/C_m); V_e = C/T_e^n.

**Input:** `C_tool`, `t_ct_min`, `t_c_min`, `C_m_per_min`, `n`, `C_m_min` — all required. **Returns:** `V_e_m_min`, `T_e_min`, `cost_per_component`.

---

### `cutting_tool_max_rate_speed`

Maximum production-rate cutting speed: T_mpr = (1/n − 1)·t_ct; V_mpr = C/T_mpr^n. Always ≥ V_e.

**Input:** `t_ct_min`, `t_c_min`, `n`, `C_m_min` — all required. **Returns:** `V_mpr_m_min`, `T_mpr_min`.

---

### `cutting_tool_break_even`

Break-even analysis comparing V_e and V_mpr: returns both speeds, their tool lives, cost per piece at each speed, and the cost ratio cost(V_mpr)/cost(V_e).

**Input:** `C_tool`, `t_ct_min`, `t_c_min`, `C_m_per_min`, `n`, `C_m_min` — all required. **Returns:** `V_e_m_min`, `V_mpr_m_min`, `cost_at_Ve`, `cost_at_Vmpr`, `cost_ratio`.

---

### `cutting_tool_machinability`

Machinability rating relative to a reference material: rating = (V_material / V_reference) × 100%. Convention: AISI B1112 at 100 m/min = 100%.

**Input:** `V_material_m_min`, `V_reference_m_min` — both required. **Returns:** `machinability_pct`.

---

### `cutting_tool_surface_finish`

Theoretical surface finish from nose radius and feed: Rt = f²/(8·r_n) [µm]; Ra ≈ Rt/4.

**Input:** `f_mm_rev` (feed per rev), `r_n_mm` (nose radius) — both required. **Returns:** `Rt_um`, `Ra_um`.

---

## Example

```
1. cutting_tool_merchant
     gamma_o_deg:10  tau_s_Pa:280e6  mu:0.5
     t1_mm:0.2  vc_m_min:150
   → phi_deg:36.0  Fc_N:247  Ft_N:118  power_W:617

2. cutting_tool_taylor_life  V_m_min:150  C_m_min:280  n:0.25
   → T_min: 28.5

3. cutting_tool_economic_speed
     C_tool:2.0  t_ct_min:3  t_c_min:5
     C_m_per_min:1.5  n:0.25  C_m_min:280
   → V_e_m_min: 187  T_e_min: 12.6

4. cutting_tool_surface_finish  f_mm_rev:0.2  r_n_mm:0.8
   → Rt_um: 6.25  Ra_um: 1.56
```
