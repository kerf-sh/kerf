# Psychrometrics and HVAC Loads

Pure-Python moist-air psychrometrics and HVAC load calculation tools per ASHRAE
Fundamentals 2021. No OCC dependency. All tools are stateless. SI state-point
quantities; HVAC load tools use IP (BTU/h, CFM, °F).

---

## When to use

Use these tools when the conversation involves: psychrometrics, moist air,
humidity, dry-bulb, wet-bulb, dew point, relative humidity, humidity ratio,
specific enthalpy, specific volume, air density, saturation pressure,
Hyland-Wexler, ASHRAE, mixing air streams, outdoor air, return air, mixed air,
sensible heat, latent heat, total heat, sensible heat ratio, SHR, cooling load,
heating load, HVAC load, BTU, CFM, cooling coil, coil apparatus dew point, ADP,
bypass factor, BF, coil leaving conditions, evaporative cooling, swamp cooler,
direct evap, altitude pressure, high-altitude site, barometric pressure, air
conditioning, HVAC design, psychrometric chart.

---

## Tools

### `psychro_state_point`

Solve the complete moist-air state from any two independent psychrometric
properties.

Supported pairs: (Tdb_C, RH), (Tdb_C, W), (Tdb_C, Twb_C), (Tdb_C, Tdp_C),
(Tdb_C, h_kJkg), (W, h_kJkg).

**Input:** at least two of `Tdb_C`, `Twb_C`, `RH` (0–1), `W` (kg/kg),
`Tdp_C`, `h_kJkg`; optional `P_Pa` (default 101 325).

**Returns:** `Tdb_C`, `Twb_C`, `RH`, `W`, `Tdp_C`, `h_kJkg`, `v_m3perkg`,
`rho_kgperm3`, warnings.

---

### `psychro_sat_pressure`

Saturation pressure of water vapour at temperature T (Hyland-Wexler, ASHRAE 2021).

**Input:** `T_C` (°C, range −100 to 200).

**Returns:** `pws_Pa`.

---

### `psychro_dew_point`

Dew-point temperature from dry-bulb and relative humidity.

**Input:** `T_C`, `RH` (0–1); optional `P_Pa`.

**Returns:** `Tdp_C`.

---

### `psychro_wet_bulb`

Wet-bulb temperature by iterative inversion of the Sprung psychrometric equation.

**Input:** `T_C`, `RH`; optional `P_Pa`.

**Returns:** `Twb_C`, `converged`.

---

### `psychro_enthalpy`

Moist-air specific enthalpy (SI): h = 1.006·T + W·(2501 + 1.86·T) kJ/kg.

**Input:** `T_C`, `W` (kg/kg).

**Returns:** `h_kJkg`.

---

### `psychro_enthalpy_ip`

Moist-air specific enthalpy (IP): h = 0.240·T + W·(1061 + 0.444·T) BTU/lb.

**Input:** `T_F`, `W_lbperlb`.

**Returns:** `h_BTUperlb`.

---

### `psychro_specific_volume`

Specific volume and density of moist air.

**Input:** `T_C`, `W` (kg/kg); optional `P_Pa`.

**Returns:** `v_m3perkg`, `rho_kgperm3`.

---

### `psychro_mix_streams`

Mix two moist-air streams (mass-weighted averages at equal pressure).

**Input:** `cfm1`, `Tdb1_C`, `W1`, `cfm2`, `Tdb2_C`, `W2`; optional `P_Pa`.

**Returns:** mixed `Tdb_C`, `W`, `h_kJkg`.

---

### `psychro_sensible_load`

Sensible heat load: Q = 1.08 × CFM × ΔT [BTU/h] (ASHRAE standard air).

**Input:** `cfm`, `delta_T_F`.

**Returns:** `Q_BTUh`.

---

### `psychro_latent_load`

Latent heat load: Q = 0.68 × CFM × ΔW_grains or 4840 × CFM × ΔW [BTU/h].

**Input:** `cfm`; exactly one of `delta_W_grains` or `delta_W_lbperlb`.

**Returns:** `Q_BTUh`.

---

### `psychro_total_load`

Total heat load: Q = 4.5 × CFM × Δh [BTU/h] (ASHRAE standard air).

**Input:** `cfm`, `delta_h_BTUperlb`.

**Returns:** `Q_BTUh`.

---

### `psychro_coil_adp`

Cooling-coil Apparatus Dew Point (ADP), Bypass Factor (BF), and SHR.

BF = (T_leaving − T_ADP) / (T_entering − T_ADP).

**Input:** `Tdb_entering_C`, `Twb_entering_C`, `Tdb_leaving_C`, `Twb_leaving_C`;
optional `P_Pa`.

**Returns:** `T_ADP_C`, `bypass_factor`, `SHR`, warnings.

---

### `psychro_coil_leaving`

Cooling-coil leaving-air conditions from entering state and applied loads.

**Input:** `Tdb_entering_C`, `W_entering`, `Q_sensible_kW`, `Q_total_kW`,
`mass_flow_kgs`; optional `P_Pa`.

**Returns:** leaving `Tdb_C`, `W`, `h_leaving_kJkg`, `SHR`.

---

### `psychro_evaporative_cooling`

Direct evaporative cooler leaving conditions (adiabatic saturation).

Tdb_leaving = Tdb − ε × (Tdb − Twb).

**Input:** `Tdb_C`, `RH`; optional `effectiveness` (default 0.80), `P_Pa`.

**Returns:** `Tdb_leaving_C`, `W_leaving`, `RH_leaving`, `h_leaving_kJkg`.

---

### `psychro_altitude_pressure`

Barometric pressure at altitude (ISA troposphere model).

P = 101325 × (1 − 2.25577×10⁻⁵ × z)^5.2559 [Pa].

**Input:** `altitude_m` (0–11 000 m).

**Returns:** `P_Pa`.

---

## Example

```
1. psychro_state_point  Tdb_C:28  RH:0.55
   → Twb_C:21.4, W:0.01322, Tdp_C:18.2, h_kJkg:61.8, rho_kgperm3:1.165

2. psychro_mix_streams  cfm1:2000  Tdb1_C:35  W1:0.018
                        cfm2:6000  Tdb2_C:24  W2:0.010
   → Tdb_C: 26.75, W: 0.012

3. psychro_sensible_load  cfm:500  delta_T_F:20
   → Q_BTUh: 10800

4. psychro_coil_adp
     Tdb_entering_C:26  Twb_entering_C:19
     Tdb_leaving_C:13  Twb_leaving_C:12
   → T_ADP_C: 10.8, bypass_factor: 0.16, SHR: 0.74
```
