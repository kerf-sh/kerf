# Wind Turbine Sizing and Performance

Pure-Python horizontal-axis wind turbine (HAWT) engineering: available wind power, Betz limit, site air density, rotor diameter sizing, rotor speed and tip-speed ratio, gearbox ratio, axial thrust force, tower overturning moment, simplified BEM Cp/Ct, power curve, annual energy production (Weibull and Rayleigh distributions), capacity factor, Jensen wake deficit, and sound pressure level at distance. No OCC dependency. All tools are stateless and never raise. References: Burton et al. (2011), Jensen (1983), IEC 61400-1:2019.

---

## When to use

Use these tools for wind turbine and wind farm engineering: wind power in the air stream, Betz limit, air density at altitude and temperature, rotor diameter from rated power, RPM and tip-speed ratio, gearbox step-up ratio for generator, axial thrust on rotor, tower base overturning moment, blade element momentum (BEM) Cp and Ct, power output at a given wind speed (cut-in/rated/cut-out regions), annual energy production (AEP) from Weibull wind statistics, Rayleigh AEP from mean wind speed, turbine capacity factor, Jensen single-wake velocity deficit for wind farm layout, wind turbine noise propagation.

---

## Tools

### `wt_available_power`

Total kinetic power in wind stream: P = ½·ρ·A·V³. **Input:** `rho` (kg/m³), `A` (swept area m²), `V` (wind speed m/s) — all required. **Returns:** `power_W`, `power_kW`.

---

### `wt_betz_limit`

Betz theoretical maximum power coefficient Cp_max = 16/27 ≈ 0.5926. No inputs required. **Returns:** `Cp_max`, `induction_factor_a`, `wake_velocity_ratio`.

---

### `wt_air_density`

ISA air density corrected for altitude and temperature via barometric formula + ideal gas law. **Input:** `altitude_m` (default 0), `temperature_c` (default 15) — both optional. **Returns:** `rho_kg_m3`, `pressure_Pa`, `temperature_K`.

---

### `wt_rotor_diameter`

Rotor diameter from rated power: D = √(8·P / (π·ρ·V³·Cp)). Cp > Betz limit is clamped with warning. **Input:** `P_rated_W`, `Cp`, `rho`, `V_rated_ms` — all required. **Returns:** `diameter_m`, `swept_area_m2`.

---

### `wt_rotor_speed`

Rotor RPM and angular velocity from tip-speed ratio: ω = TSR·V/R. Warns if tip speed > 80 m/s. **Input:** `V_ms`, `tsr`, `diameter_m` — all required. **Returns:** `omega_rad_s`, `rpm`, `tip_speed_ms`.

---

### `wt_gearbox_ratio`

Required step-up gearbox ratio from rotor to generator speed: ratio = generator_rpm / rotor_rpm (rounded up to integer). **Input:** `rotor_rpm`, `generator_rpm` — both required. **Returns:** `ratio_exact`, `ratio_integer`, `generator_rpm_actual`.

---

### `wt_thrust_force`

Axial rotor thrust: T = ½·ρ·A·V²·Ct. Default Ct = 8/9 (Betz optimum). **Input:** `rho`, `A`, `V` (required); `Ct` (optional). **Returns:** `thrust_N`, `thrust_kN`.

---

### `wt_overturning_moment`

Tower base overturning moment (first-order): M = Thrust × hub_height. **Input:** `thrust_N`, `hub_height_m` — both required. **Returns:** `moment_Nm`, `moment_kNm`.

---

### `wt_blade_element_momentum`

Simplified Glauert BEM analysis: iterates axial and tangential induction factors per annulus, integrates to Cp and Ct. No tip-loss correction. Preliminary design use only. **Input:** `tsr` (required); `n_blades` (default 3), `chord_r_ratio` (default 0.06), `n_annuli` (default 20) (optional). **Returns:** `Cp`, `Ct`, `annuli` (per-annulus details).

---

### `wt_power_curve`

Power output at a given wind speed: parked below cut-in, cubic ramp to rated, flat at rated, parked above cut-out. **Input:** `V_ms`, `V_cutin`, `V_rated`, `V_cutout`, `P_rated_W` — all required. **Returns:** `power_W`, `power_kW`, `region`, `capacity_factor_instant`.

---

### `wt_weibull_aep`

Annual energy production (AEP) from Weibull wind distribution: AEP = T·∫P(v)·f_Weibull(v)dv. **Input:** `k` (shape), `c_ms` (scale), `V_cutin`, `V_rated`, `V_cutout`, `P_rated_W` — all required; `hours_per_year` (default 8760). **Returns:** `aep_kWh`, `aep_MWh`, `capacity_factor`, `weibull_mean_ms`.

---

### `wt_rayleigh_aep`

AEP using Rayleigh distribution (Weibull k = 2): scale c = 2·v_mean/√π. **Input:** `v_mean_ms`, `V_cutin`, `V_rated`, `V_cutout`, `P_rated_W` — all required. **Returns:** `aep_kWh`, `aep_MWh`, `capacity_factor`, `rayleigh_c_ms`.

---

### `wt_capacity_factor`

Capacity factor: CF = AEP / (P_rated × 8760 h). Warns if CF < 0.20. **Input:** `aep_kWh`, `P_rated_W` (required); `hours_per_year` (optional). **Returns:** `capacity_factor`, `capacity_factor_percent`.

---

### `wt_jensen_wake`

Jensen (1983) single-wake velocity deficit: u/u0 = 1 − (1 − √(1−Ct)) × (D/(D + 2·k_w·x))². Typical k_w: 0.04–0.06 onshore, 0.02–0.04 offshore. **Input:** `u0_ms`, `Ct`, `x_m`, `D_m` (required); `k_w` (default 0.04). **Returns:** `u_wake_ms`, `deficit_fraction`, `deficit_percent`, `power_ratio`.

---

### `wt_sound_pressure`

SPL at observer distance (hemispherical propagation, ISO 9613-2 simplified): SPL = Lw − 10·log10(2π·r²). **Input:** `Lw_dB` (sound power level), `distance_m` — both required. **Returns:** `spl_dBA`.

---

## Example

```
1. wt_air_density  altitude_m:500  temperature_c:20
   → rho_kg_m3: 1.162

2. wt_rotor_diameter
     P_rated_W:2e6  Cp:0.45  rho:1.162  V_rated_ms:12
   → diameter_m: 82.4  swept_area_m2: 5331

3. wt_rotor_speed  V_ms:12  tsr:8  diameter_m:82.4
   → rpm: 22.2  tip_speed_ms:96  (warning: tip > 80 m/s; consider TSR 7)

4. wt_weibull_aep
     k:2.0  c_ms:9.0
     V_cutin:3  V_rated:12  V_cutout:25  P_rated_W:2e6
   → aep_MWh:6150  capacity_factor:0.35

5. wt_jensen_wake  u0_ms:9  Ct:0.8  x_m:500  D_m:82.4  k_w:0.04
   → u_wake_ms:7.6  deficit_percent:15.5  power_ratio:0.60
```
