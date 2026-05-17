# Hydropower Plant and Turbine Engineering

Pure-Python IEC 60193 / Warnick hydropower engineering tools. No OCC dependency.
All tools are stateless — they compute and return results; no DB write.
Units: SI (m, m³/s, W, Pa).

Authoritative standards:
- **IEC 60193 (1999)** — *Hydraulic Turbines, Storage Pumps and Pump-Turbines —
  Model Acceptance Tests* — dimensionless specific speed definition, similarity
  laws, model-to-prototype scaling.
- **Warnick, C.C. (1984)** — *Hydropower Engineering*, Prentice-Hall — turbine
  selection by head and specific speed, K factor runner-speed estimates.
- **Gordon, J.L. (1999)** — "Turbine selection for small low head hydro power
  projects," *Proceedings of the 5th Int. Symposium on Low Head Hydro* — σ_crit
  cavitation correlation.
- **Joukowsky, N. (1900)** — "Über den hydraulischen Stoss in Wasserleitungsröhren"
  — water-hammer pressure-rise formula ΔP = ρ·a·ΔV.
- **Allievi, L. (1902)** — *Teoria del colpo d'ariete* — finite-closure water-hammer
  treatment.
- **Thoma, D. (1910)** — cavitation number σ and stability criterion for surge tanks.
- **USBR Engineering Monograph 20 (1967)** — *Design of Small Canal Structures* —
  penstock sizing and water-hammer reference.
- **IEC 62600-100** — small hydropower for reference.

---

## When to use

Hydroelectric, hydro plant, turbine selection, Pelton, Francis, Kaplan, Bulb
turbine, Turgo, Crossflow, penstock sizing, penstock friction, penstock wall
thickness, water hammer, Joukowsky pressure, surge tank, cavitation, Thoma sigma,
runaway speed, flow-duration curve, annual energy, micro-hydro, run-of-river,
small hydro, hydropower design.

---

## Tools

### `hydro_plant_power`

Hydropower shaft power and hydraulic power.

```
P_hydraulic = ρ·g·Q·H_net          (W)
P_shaft     = η·P_hydraulic         (W)
```

**Input:** `Q` (m³/s), `H_net` (m), `eta` (default 0.88), `rho` (default 1000).

**Returns:** `P_hydraulic_W`, `P_shaft_W`, `P_shaft_kW`, `P_shaft_MW`.

**Standards alignment:** IEC 60193 §4.2 (hydraulic power definition); η = 0.88
is representative of modern Francis turbines at rated load; actual η from
IEC 60193 model tests for production-grade design.

---

### `hydro_turbine_type`

Select turbine type from net head, flow, and optionally runner speed — IEC
dimensionless specific speed Ns or head-range heuristics.

```
Ns = n·√P / H_net^(5/4)             (IEC 60193 dimensionless specific speed)
```

Head ranges (Warnick Table 2.1):
- Pelton: H > 150 m (multi-nozzle down to 50 m)
- Francis: 40–700 m
- Kaplan/Bulb: H < 40 m
- Crossflow/Banki: < 50 m

**Input:** `H_net` (m), `Q` (m³/s), `n_rpm` (optional), `P_kW` (optional).

**Returns:** `turbine_type`, `Ns`, `alternatives`, `head_range_ok`, `warnings`.

**Standards alignment:** IEC 60193 §2.2 (dimensionless specific speed);
Warnick (1984) Table 2.1 (head/Ns ranges); head-range boundaries vary by
source — alternatives listed when the site sits at a type boundary.

---

### `hydro_runner_speed`

Estimate runner design speed: n ≈ K·√H (rpm). K factors by type (Warnick Table 3.1):
Pelton 30, Francis 50, Kaplan 150.

**Input:** `H_net` (m), `turbine_type` (default `'Francis'`).

**Returns:** `n_rpm_approx`, `K_used`.

**Standards alignment:** Warnick (1984) §3.2 speed estimates. Synchronous speed
must be matched to generator pole count via `hydro_sync_speed_poles`.

---

### `hydro_sync_speed_poles`

Find nearest synchronous generator speeds and pole counts.

```
n_sync = 120·f / p                  (rpm; p = pole pairs, even integers)
```

**Input:** `n_runner_rpm`, `f_hz` (default 50).

**Returns:** `poles_lower`, `n_sync_lower_rpm`, `poles_higher`, `n_sync_higher_rpm`.

**Standards alignment:** IEC 60034-1 (synchronous machine ratings); generator
pole count must be an even integer; turbine speed selected to match nearest
synchronous speed.

---

### `hydro_penstock_diameter`

Economic penstock diameter from flow and target velocity.

```
D = √(4·Q / (π·V_economic))         (m)
```

**Input:** `Q` (m³/s), `V_economic` (m/s, default 3.0).

**Returns:** `D_m`, `A_m2`.

**Standards alignment:** USBR Monograph 20 §2 (V_economic = 2–4 m/s for steel
penstocks; higher for short penstocks where friction loss is minor). The economic
diameter minimises combined capital (larger pipe) + energy-loss (smaller pipe)
annual costs.

---

### `hydro_penstock_friction`

Darcy-Weisbach friction head loss in penstock.

```
h_f = f·(L/D)·V²/(2g)               (m)
Re  ≈ V·D / ν  (ν_water = 1.004×10⁻⁶ m²/s at 20°C)
```

**Input:** `Q`, `D`, `L`, `f` (default 0.015 for steel at Re~10⁶).

**Returns:** `h_f_m`, `V_m_s`, `Re_approx`.

**Standards alignment:** Darcy-Weisbach (Darcy 1857; Weisbach 1845); friction
factor from Moody chart / Colebrook-White. Default f = 0.015 corresponds to
commercial steel ε = 0.045 mm at Re ≈ 10⁶ (Moody chart §5.3).

---

### `hydro_penstock_wall`

Minimum penstock wall thickness — Barlow thin-wall (hoop-stress) formula.

```
t = P·D / (2·σ_allow·e) + c_corr    (m)   [Barlow's formula]
```

**Input:** `D` (m), `P_internal_Pa`, `sigma_allow_Pa` (default 120 MPa for
grade A516-70 steel), `weld_efficiency` (default 0.85), `corrosion_mm` (default 2).

**Returns:** `t_calc_mm`, `t_total_mm`.

**Standards alignment:** ASME B31.3 / ASME BPVC §VIII thin-wall formula; USBR
Monograph 20 §3 (penstock wall thickness). σ_allow = 0.72·SMYS × weld efficiency
is the USBR criterion; SMYS for A516-70 = 260 MPa → σ_allow ≈ 187 MPa at 0.72
with E=1.0 (use supplier-specified SMYS for actual design).

---

### `hydro_water_hammer_joukowsky`

Joukowsky rapid-closure water-hammer pressure rise.

```
ΔP = ρ·a·ΔV                         [Joukowsky 1900]
dH = ΔP / (ρ·g)    (head rise, m)
```

**Input:** `V` (m/s, flow velocity before closure), `a_wave` (m/s, wave
celerity; typically 900–1200 m/s for steel penstocks), `rho` (default 1000).

**Returns:** `dP_Pa`, `dP_bar`, `dH_m`.

**Standards alignment:** Joukowsky (1900) formula — exact for instantaneous
valve closure (T_close < 2L/a). Wave celerity: a = √(K/ρ / (1 + D·K/(E·t)))
per Halliwell (1963) — calculate a separately; typical 900–1200 m/s for steel.

---

### `hydro_water_hammer_allievi`

Allievi finite-closure water-hammer (slow closure regime if T_close > T_critical).

```
T_critical = 2L/a         (Joukowsky → Allievi transition)
Slow (Michaud):  ΔH = 2·L·V / (g·T_close)   when T_close > T_critical
Rapid (Joukowsky): ΔH = a·V/g               when T_close ≤ T_critical
H_total_max = H_static + ΔH_max
```

**Input:** `H_static`, `V`, `a_wave`, `L`, `T_close`, `rho`.

**Returns:** `T_critical_s`, `regime`, `dH_max_m`, `H_total_max_m`,
`overpressure_ratio`, `warnings`.

**Standards alignment:** Allievi (1902); Michaud (1878) slow-closure formula;
USBR Monograph 20 §3.3 (water-hammer analysis for penstocks).

---

### `hydro_surge_tank`

Surge-tank sizing — Thoma stability criterion.

```
A_Thoma = A_pipe·L / (2·H_friction_effective)   [Thoma 1910]
```

Also returns oscillation period and energy-balance area for maximum upsurge.

**Input:** `Q`, `a_wave`, `L`, `H_net`, `D_penstock` (all required),
`max_upsurge_m` (optional).

**Returns:** `A_thoma_m2`, `T_oscillation_s`, `A_energy_m2` (if upsurge given).

**Standards alignment:** Thoma (1910) stability criterion — below A_Thoma the
governor hunt (instability) occurs; actual A must exceed A_Thoma with a safety
margin of 1.2–1.5 (USBR practice). Oscillation period T = 2π√(A_s·L/(g·A_pipe)).

---

### `hydro_thoma_cavitation`

Thoma cavitation check.

```
σ_plant = (H_atm − H_vapor − H_s) / H_net    [Thoma 1910]
σ_crit  from Gordon (1999) regression: σ_crit ≈ 6.0·Ns²  (dimensionless Ns)
Cavitation risk = "low" if σ_plant > σ_crit, else "high"
```

**Input:** `H_net`, `H_s` (draft head, m), `turbine_type`, `n_rpm`, `Q`,
`P_vapor_Pa`, `P_atm_Pa`, `elevation_m`.

**Returns:** `sigma_plant`, `sigma_crit`, `cavitation_risk`.

**Standards alignment:** Thoma (1910) cavitation number; Gordon (1999) σ_crit
correlation; IEC 60193 §7.4 (cavitation index measurement in model tests).
H_s > 0 → turbine above tailwater (more cavitation risk); H_s < 0 → submerged
runner (less risk). Setting elevation per IEC 60193 §4.4.3.

---

### `hydro_runaway_speed`

Turbine runaway (load-rejection) speed.

Multipliers (Warnick Table 4.1): Pelton 1.8×, Francis 1.8×, Kaplan 2.3×.

**Input:** `n_rpm`, `turbine_type`.

**Returns:** `n_runaway_rpm`, `runaway_factor`.

**Standards alignment:** Warnick (1984) Table 4.1; IEC 60193 §4.2 (runaway
speed test conditions). Generator and penstock must be designed for runaway speed
and the corresponding hydraulic transient.

---

### `hydro_flow_duration_energy`

Annual energy from a discretised flow-duration curve.

```
E_annual = Σ P_shaft(Qi)·Δh_i·8760    (MWh)
```
where Δh_i = fraction of hours in each flow interval.

**Input:** `flow_fractions` (fraction of time in each flow band), `Q_design`,
`H_net`, `eta`.

**Returns:** `E_annual_MWh`, `capacity_factor`, `plant_factor`, `hours_generating`,
`spill_fraction`.

**Standards alignment:** IEC 62600-100 (resource assessment); flow-duration curve
analysis from USGS or local gauge data; capacity factor = E_annual / (P_rated × 8760).

---

### `hydro_pelton_jet`

Pelton jet and bucket sizing.

```
V_jet = Cv·√(2·g·H_net)              (jet velocity, m/s; Cv ≈ 0.97)
d_jet = √(4·Q / (n_jets·π·V_jet))   (jet diameter, m)
B_bucket = 3.2·d_jet                 (bucket width; Warnick §6.3)
u_opt = φ·V_jet  where φ = 0.46      (optimum peripheral velocity)
```

**Input:** `H_net`, `Q`, `n_jets` (default 1), `Cv` (default 0.97),
`D_runner_m` (optional).

**Returns:** `V_jet_m_s`, `d_jet_m`, `B_bucket_m`, `u_opt_m_s`, `n_opt_rpm`.

**Standards alignment:** Warnick (1984) §6.3 (Pelton jet sizing); IEC 60193
§4.3 (model similarity laws); Cv = 0.97 per standard nozzle discharge coefficient.

---

### `hydro_micro_quick`

Quick-sizing utility for micro-hydro plants (< 100 kW).

Auto-sizes penstock (V_economic = 2.5 m/s), estimates friction losses, returns
net head, shaft power, and turbine type.

**Input:** `H_gross` (m), `Q`, `penstock_length` (m, default 0),
`eta_overall` (default 0.70).

**Returns:** `H_net_m`, `P_shaft_kW`, `turbine_type`, `D_penstock_m`.

**Standards alignment:** IEC 62600-100 micro-hydro scoping; overall efficiency
0.70 is conservative for micro-hydro (turbine × generator × civil losses).

---

## Example

```
1. hydro_turbine_type  H_net:45  Q:8.5
   → turbine_type:"Francis"  Ns:120  [IEC 60193; Warnick Table 2.1]

2. hydro_plant_power  Q:8.5  H_net:45  eta:0.88
   → P_shaft_kW:3300  [P = η·ρ·g·Q·H; IEC 60193 §4.2]

3. hydro_penstock_diameter  Q:8.5  V_economic:4.0
   → D_m:1.64  [USBR Monograph 20 §2]

4. hydro_water_hammer_allievi  H_static:45  V:4.0  a_wave:1200  L:300  T_close:5.0
   → T_critical_s:0.5  regime:"slow"  dH_max_m:18.3  overpressure_ratio:0.41
   [Allievi slow-closure: ΔH=2LV/(gT_c); T_close=5 >> T_crit=0.5]
```
