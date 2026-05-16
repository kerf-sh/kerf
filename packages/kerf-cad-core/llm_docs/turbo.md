# Turbomachinery Blade & Stage Design

Pure-Python turbomachinery tools covering the Euler work equation, axial and
centrifugal velocity triangles, dimensionless performance groups, specific speed,
Cordier diagram, degree of reaction, full stage analysis, centrifugal impeller
design, fan/pump affinity laws, isentropic/polytropic efficiency, and surge/choke
margin. No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use when the user asks about: turbomachinery, turbine, compressor, fan, pump,
centrifugal, axial, velocity triangles, Euler equation, blade speed, whirl velocity,
degree of reaction, flow coefficient, work coefficient, loading coefficient, specific
speed, dimensionless specific speed, Cordier diagram, Cordier line, specific diameter,
impeller, centrifugal impeller, slip factor, affinity laws, fan laws, pump laws,
speed change, impeller trim, isentropic efficiency, polytropic efficiency, surge
margin, choke margin, Lieblein diffusion factor, de Haller number.

---

## Tools

### `turbo_euler_work`

Euler turbomachine specific work: W = U × ΔCθ.

**Input:** `U` (required) — blade speed (m/s); `dCtheta` (required) — change in whirl velocity (m/s); positive = compressor, negative = turbine

**Output:** `W_specific_J_kg`

---

### `turbo_velocity_triangles_axial`

Axial turbomachinery stage velocity triangles (constant axial velocity assumed).

**Input:** `U`, `Ca`, `alpha1_deg`, `alpha2_deg` (all required)

**Output:** absolute angles α, relative angles β, absolute velocities C and W, whirl components Cθ, `euler_work_J_kg`

---

### `turbo_velocity_triangles_centrifugal`

Velocity triangles at the exit of a centrifugal impeller.

**Input:**
- `U2`, `Cr2` (required) — tip blade speed and radial velocity at exit (m/s)
- `beta2_deg` — blade exit angle from radial (default −30°, backward sweep)
- `slip_factor` — σ (default 0.9)

**Output:** ideal and actual exit whirl velocities, absolute/relative exit velocities, `euler_work_J_kg`

---

### `turbo_dimensionless_groups`

Flow coefficient φ, loading coefficient ψ, power coefficient C_P, and blade Mach number M_U.

**Input:** `U`, `Ca`, `dCtheta` (all required); optional `rho` (default 1.225 kg/m³), `blade_speed_sound`

**Output:** `phi`, `psi`, `C_P`, `M_U` (if speed of sound provided)

---

### `turbo_specific_speed_diameter`

Dimensionless specific speed Ω_s and specific diameter Δ_s for machine classification.

**Input:** `Q` (m³/s), `gH` (J/kg), `omega` (rad/s) (all required); optional `D` (m) for Δ_s

**Output:** `Omega_s`, `Delta_s` (if D provided); Ω_s < 1 → radial, 1–3 → mixed, > 3 → axial

---

### `turbo_cordier_optimum`

Cordier-line optimum specific diameter Δ_s_opt for a given Ω_s (log-polynomial fit, Dixon Fig 1.5).

**Input:** `Omega_s` (required); reliable range 0.2–10.0

**Output:** `Delta_s_opt`; warns if outside reliable range

---

### `turbo_degree_of_reaction`

Stage degree of reaction: R = 1 − (Cθ1 + Cθ2) / (2·U).

**Input:** `Ctheta1`, `Ctheta2`, `U` (all required)

**Output:** `degree_of_reaction`; R = 0.5 = symmetric, R = 0 = impulse; warns for R < 0

---

### `turbo_axial_stage`

Full axial compressor or turbine stage analysis with loading diagnostics.

**Input:** `U`, `Ca`, `alpha1_deg`, `alpha2_deg` (all required); optional `rho`, `is_compressor` (default true), `chord`, `span`, `nu`

**Output:** velocity triangles, stage work, degree of reaction, Lieblein diffusion factor DF and de Haller W2/W1 (compressor), blade loading ΔCθ/U (turbine); warns if DF > 0.6 or W2/W1 < 0.72

---

### `turbo_centrifugal_impeller`

Centrifugal pump/compressor impeller design-point analysis (Euler head, slip, velocity triangles, NPSH estimate).

**Input:**
- `n_rpm`, `D2_m`, `b2_m`, `D1_tip_m`, `D1_hub_m` (all required)
- `beta2_deg` (default −30°), `Z` (blade count, default 8), `rho` (default 1000 kg/m³), `slip_model` (`"stanitz"` default or `"wiesner"`)

**Output:** `U2_m_s`, `Euler_head_m`, `slip_factor`, exit velocity triangles, `vol_flow_m3_s`, `NPSH_inception_m`

---

### `turbo_fan_affinity`

Fan/pump affinity laws for speed change and/or impeller trim.

**Input:** `Q1`, `H1`, `P1`, `n1`, `n2` (all required); optional `D1`, `D2` for trim

**Output:** `Q2`, `H2`, `P2`; warns if trim ratio < 0.70

---

### `turbo_stage_efficiency`

Isentropic and polytropic efficiency for a turbomachinery stage.

**Input:**
- `W_actual`, `W_isentropic` (both required, J/kg)
- `polytropic_n` — optional polytropic index
- `gamma` — ratio of specific heats (default 1.4 for air)
- `stage_type` — `"compressor"` (default) or `"turbine"`

**Output:** `eta_isentropic`, `eta_polytropic` (if n provided), `preheat_factor`

---

### `turbo_surge_choke_margin`

Surge margin and choke margin for a compressor/fan stage.

**Input:** `phi_op`, `phi_surge`, `phi_choke` (all required); optional `min_surge_margin` (default 0.15), `min_choke_margin` (default 0.10)

**Output:** `surge_margin`, `choke_margin`, `in_surge` flag; critical warning if SM < 0

---

## Example

```
1. turbo_specific_speed_diameter
     Q:0.5  gH:200  omega:314  D:0.25
   → Omega_s:1.8  Delta_s:2.1   (mixed-flow)

2. turbo_axial_stage
     U:250  Ca:150  alpha1_deg:0  alpha2_deg:35
   → euler_work:13125 J/kg  degree_of_reaction:0.57
   → diffusion_factor:0.48  de_haller:0.78  (OK, no stall risk)

3. turbo_fan_affinity
     Q1:1.0  H1:80  P1:12000  n1:1450  n2:1200
   → Q2:0.828  H2:54.8  P2:6784
```
