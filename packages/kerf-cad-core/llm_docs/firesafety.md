# Fire Safety and Fire Protection Engineering

Pure-Python fire protection engineering tools. No OCC dependency. All tools are
stateless.

Authoritative standards:
- **NFPA 13 (2022)** — *Standard for the Installation of Sprinkler Systems* —
  density/area method, K-factor, Hazen-Williams hydraulic calculations.
- **NFPA 20 (2022)** — *Standard for the Installation of Stationary Pumps for
  Fire Protection* — fire pump three-point performance curve requirements.
- **NFPA 92 (2021)** — *Standard for Smoke Control Systems* — Heskestad
  axisymmetric plume model, atrium smoke exhaust.
- **NFPA 101 (2021)** — *Life Safety Code* — occupant load, egress capacity,
  travel distance, common path, dead-end limits.
- **IBC 2021** — *International Building Code*, Table 601 — fire-resistance
  ratings by occupancy and construction type.
- **ASTM E119-22** — *Standard Test Methods for Fire Tests of Building Construction*
  — temperature-time curve, unexposed-surface temperature limit.
- **SFPE Handbook of Fire Protection Engineering**, 5th ed. — Alpert ceiling-jet
  correlations (§2-2), Heskestad plume model (§2-1), t-squared fire model,
  RTI-based detector activation (§2-9).

---

## When to use

Fire protection, fire sprinkler, sprinkler hydraulic, NFPA 13, sprinkler demand,
K-factor, Hazen-Williams, fire pump, NFPA 20, pump sizing, water supply, hydrant
flow test, static pressure, residual pressure, egress, life safety, NFPA 101,
occupant load, exit width, travel distance, common path, dead-end corridor,
design fire, t-squared, heat release rate, HRR, detector activation, ceiling jet,
Alpert, RTI, sprinkler activation, smoke control, atrium exhaust, NFPA 92,
Heskestad plume, fire resistance, ASTM E119, fire rating, IBC occupancy, required
fire rating.

---

## Tools

### `sprinkler_hydraulic_demand`

NFPA 13 density/area sprinkler hydraulic demand. Uses K = Q/√P, Hazen-Williams
friction, and hose-stream allowance to determine required source pressure.

```
K = Q_gpm / √(P_psi)              [NFPA 13 §24.1.1]
Q_sprinkler = density_gpm_ft2 × area_ft2
P_source = P_remote + ΔP_friction + hose_demand
Hazen-Williams: ΔP = 4.52·Q^1.85 / (C^1.85·d^4.87)  (psi per ft)
```

**Input:** `occupancy_class`, `k_factor`, `pipe_d_inch`, `pipe_length_ft`,
`elevation_diff_ft`, `density_override`, `area_override`, `hw_coeff` (default 120).

**Returns:** `Q_total_gpm`, `P_required_psi`, `design_density`, `design_area_ft2`,
warnings.

**Standards alignment:**
- NFPA 13-2022 §19 (occupancy classification); Table 19.3.3.1.1 (density/area
  curves): light hazard 0.10 gpm/ft² over 1500 ft²; OH-1 0.15/2000; OH-2 0.20/2000;
  EH-1 0.30/2500; EH-2 0.40/2500.
- NFPA 13 §24.1.1 (K-factor); Table 24.1.1 (standard K=5.6, large-drop K=11.2,
  ESFR K=14.0–25.2).
- NFPA 13 §24.3.2 (hose-stream allowance: 100 gpm light hazard, 250 gpm OH,
  500 gpm EH).
- Hazen-Williams coefficient C=120 (new Schedule 40 steel per NFPA 13 §22.5.2.1).

---

### `fire_pump_sizing`

NFPA 20 fire pump three-point performance curve.

```
Rated point:      Q_r, P_r                   [NFPA 20 §4.28.1]
Churn (shutoff):  Q=0, P ≥ 1.10·P_r         [§4.28.2.2, ≥110% rated head]
150% flow:        Q=1.5·Q_r, P ≥ 0.65·P_r  [§4.28.2.3, ≥65% rated head]
```

**Input:** `rated_flow_gpm`, `rated_head_psi`.

**Returns:** rated/150%/churn points with flow, pressure, and pass/fail flags.

**Standards alignment:** NFPA 20-2022 §4.28.2 (pump performance curve requirements);
the three-point curve ensures adequate head at overload (150%) and prevents
excessive pressure at shutoff (≤ 140% per §4.28.2.2).

---

### `water_supply_adequacy`

Available water supply vs. system demand from hydrant flow test data.

```
Supply curve: P(Q) = P_static − (P_static − P_residual)·(Q/Q_residual)^1.85
Available P at Q_required = P(Q_required) ≥ P_required
```

**Input:** `static_pressure_psi`, `residual_pressure_psi`, `residual_flow_gpm`,
`required_flow_gpm`, `required_pressure_psi`.

**Returns:** `available_pressure_psi`, `adequate` (bool), `margin_psi`.

**Standards alignment:** NFPA 291-2019 (hydrant flow testing procedure); the
1.85-power supply curve is consistent with the Hazen-Williams C-factor basis;
minimum 10 psi residual pressure required at the source connection point during
maximum demand per NFPA 13 §24.2.1.

---

### `egress_analysis`

NFPA 101 egress analysis: occupant load, exit count, exit width capacity, travel
distance, common path, and dead-end limits.

```
Occupant load = floor_area_ft2 / OLF               [NFPA 101 §7.3.1.2]
Exit capacity = Σ(exit_widths) / 0.2 in-per-person (stairs)
                                  0.15 in-per-person (level egress)
Time to egress ≈ occupant_load / (exit_capacity/min)
```

**Input:** `floor_area_ft2`, `occupancy_type`, `num_exits`, `exit_widths_in`,
`travel_distance_ft`, `common_path_ft`, `dead_end_ft`, `exit_component`.

**Returns:** `occupant_load`, `exit_capacity`, `travel_ok`, `common_path_ok`,
`dead_end_ok`, `time_to_egress_min`, code-violation flags.

**Standards alignment:**
- NFPA 101-2021 §7.3.1.2 (occupant load factors, Table 7.3.1.2): business
  100 ft²/person; assembly-concentrated 7 ft²/person; etc.
- §7.3.3.1 (exit width: stairs 0.2 in/person, level 0.15 in/person, minimum
  28 in per §7.2.1.2.1).
- §7.6.1 (travel distance: business 200–300 ft; assembly 150–250 ft; sprinklered
  buildings get +50–100 ft credit depending on occupancy).
- §7.5.1.1.1 (common path of travel: 75 ft non-sprinklered, 100 ft sprinklered).
- §7.5.1.2 (dead-end corridors: 20 ft non-sprinklered, 50 ft sprinklered).

---

### `design_fire_tsquared`

t-squared design fire heat release rate (HRR): Q = α·t².

Growth classes (NFPA 92-2021 Table B.2):

| Class | α (kW/s²) | t to 1 MW (s) |
|-------|-----------|---------------|
| slow | 0.00293 | 600 |
| medium | 0.01172 | 300 |
| fast | 0.04689 | 150 |
| ultra_fast | 0.18756 | 75 |

**Input:** `time_s`, `growth_class` (default `'medium'`), `alpha_override`,
`max_hrr_kw`.

**Returns:** `HRR_kW`, `alpha_kW_s2`, `time_to_1MW_s`.

**Standards alignment:** NFPA 92-2021 Annex B (t-squared fire model); growth
class selection from SFPE Handbook 5th ed. §2-1 (Table 2-1.1 — occupancy-specific
HRR rates). Ultra-fast applies to pool fires, fast to cartons/mail bags, medium
to office furnishings, slow to heavy timber.

---

### `detector_activation_time`

Sprinkler/detector activation time via Alpert ceiling-jet correlations and
RTI (Response Time Index) model.

```
Alpert ceiling-jet (SFPE §2-2):
  T_gas_r  = T_amb + 5.38·Q^(2/3) / (r·H^(1/3))     for r/H > 0.18
  T_gas_0  = T_amb + 16.9·Q^(2/3) / H^(5/3)         for r/H ≤ 0.18
  V_jet  = 0.195·Q^(1/3)·H^(1/2) / r               (m/s)

RTI activation model (SFPE §2-9):
  dT_det/dt = (V_jet)^0.5 / RTI × (T_gas − T_det)
  Activation when T_det reaches detector_temp_c.
```

**Input:** `hrr_kw`, `ceiling_height_m`, `radial_distance_m`, `rti`, `detector_temp_c`,
`ambient_temp_c`.

**Returns:** `ceiling_jet_temp_C`, `ceiling_jet_velocity_m_s`, `t_activation_s`,
warnings.

**Standards alignment:** Alpert (1972) ceiling-jet correlations (SFPE Handbook
5th ed. §2-2, Table 2-2.2); RTI model per Heskestad & Smith (1976); NFPA 72-2022
§17.6.3 (RTI definition — m^0.5·s^0.5; typical QR: RTI 50; SR: RTI 100–200).

---

### `smoke_control_exhaust`

NFPA 92 atrium smoke exhaust — Heskestad axisymmetric plume model.

```
Mass flow rate at height z (Heskestad 1984, SFPE §2-1):
  ṁ = 0.071·Q_c^(1/3)·(z − z_0)^(5/3) + 0.0018·Q_c    (kg/s)
  z_0 = −1.02·D_f + 0.083·Q^(2/5)·D_f^0      (virtual origin)

Exhaust rate = ṁ / ρ_smoke                  (m³/s)
```

**Input:** `hrr_kw`, `atrium_height_m`, `smoke_layer_height_m`.

**Returns:** `exhaust_cfm`, `exhaust_m3s`, `plume_mass_flow_kg_s`, warnings.

**Standards alignment:** NFPA 92-2021 §5.5.2 (algebraic plume equations);
Heskestad (1984) "Engineering Relations for Fire Plumes," *Fire Safety Journal*,
7(1):25-32; SFPE Handbook 5th ed. §2-1 (Eq. 2-1.12). Assumes axisymmetric
steady fire — not applicable to wall fires or fires in corridors.

---

### `fire_resistance_heat_transfer`

1-D steady-state heat transfer through a fire-rated assembly. Checks ASTM E119
unexposed-surface temperature limit.

```
R_total = Σ(t_i / k_i)           (thermal resistance, K·m²/W)
q = (T_fire − T_amb) / R_total   (heat flux, W/m²)
T_unexposed = T_amb + q·R_ambient
ASTM E119 limit: T_unexposed ≤ T_amb + 139°C    [ASTM E119-22 §7.4.2]
```

**Input:** `assembly_layers` (list of `{name, thickness_mm, conductivity_W_mK}`),
`fire_side_temp_c` (default 927°C — ASTM E119 standard time-temperature curve
at 60 min), `ambient_temp_c` (default 20).

**Returns:** `T_unexposed_C`, `passes_E119`, per-interface temperatures, heat flux.

**Standards alignment:** ASTM E119-22 §7.4.2 (temperature limit 139°C above
ambient on unexposed surface); §5.3 (standard time-temperature curve: 538°C at
5 min, 704°C at 10 min, 927°C at 60 min). The 1-D steady-state model is
conservative for short durations; actual test performance involves unsteady
conduction — use for assembly screening only.

---

### `required_fire_rating`

Minimum fire-resistance rating (hours) by occupancy and building height —
**IBC 2021 Table 601**.

Optional 1-hour sprinkler credit per IBC §504.

**Input:** `occupancy_group`, `building_height_stories`, `sprinklered`.

**Returns:** `bearing_wall_hr`, `non_bearing_wall_hr`, `floor_ceiling_hr`, notes.

**Standards alignment:** IBC 2021 Table 601 (fire-resistance rating requirements
for building elements by construction type); sprinkler credit per IBC §504.2
(one-hour reduction in bearing wall for fully sprinklered buildings, where
permitted). Construction type not explicitly selected — tool uses the most
conservative (Type IIB) applicable rating for the given occupancy and height.

---

## Example

```
1. design_fire_tsquared  time_s:300  growth_class:"fast"
   → HRR_kW:4220  time_to_1MW_s:150  [NFPA 92 Annex B; Q = α·t²]

2. smoke_control_exhaust  hrr_kw:4220  atrium_height_m:15  smoke_layer_height_m:6
   → plume_mass_flow:25.4 kg/s  exhaust_m3s:52.8  exhaust_cfm:112000
   [Heskestad SFPE §2-1; NFPA 92 §5.5.2]

3. detector_activation_time  hrr_kw:1000  ceiling_height_m:4  radial_distance_m:2.5
                              rti:80  detector_temp_c:74
   → ceiling_jet_temp_C:108  t_activation_s:38  [Alpert; RTI model SFPE §2-9]

4. egress_analysis  floor_area_ft2:8000  occupancy_type:"business"  num_exits:2
                    exit_widths_in:[44,44]  travel_distance_ft:180
   → occupant_load:80  exit_capacity:293  travel_ok:true  [NFPA 101-2021 §7]

5. sprinkler_hydraulic_demand  occupancy_class:"ordinary_hazard_group_1"
                                k_factor:5.6  pipe_d_inch:2.0  pipe_length_ft:100
   → Q_total_gpm:235  P_required_psi:47  [NFPA 13-2022 §19/§24]
```
