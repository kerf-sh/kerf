# Boiler and Steam Plant Engineering

Pure-Python steam and boiler plant calculations: IAPWS-IF97-style steam properties, boiler efficiency, fuel firing, combustion air, blowdown, deaerator/economizer energy balances, equivalent evaporation, pipe sizing, flash steam, condensate recovery, steam trap capacity, and safety valve sizing. No OCC dependency. All tools are stateless and never raise. References: ASME PTC 4-2013, API 520, Spirax Sarco.

---

## When to use

Use these tools for steam plant and boiler engineering: saturation temperature, saturation pressure, saturated/superheated steam enthalpy and specific volume, boiler heat duty, steam output from fuel, input-output thermal efficiency, ASME PTC 4 heat-loss efficiency, fuel firing rate from HHV, combustion air and excess air, continuous blowdown from TDS and cycles of concentration, blowdown heat loss, feedwater mass/energy balance, deaerator energy balance, economizer preheat duty, equivalent evaporation and factor of evaporation, boiler horsepower, steam pipe velocity and Darcy-Weisbach pressure drop, flash steam fraction, condensate heat recovery, steam trap orifice capacity, Napier safety valve sizing.

---

## Tools

### `boiler_tsat_from_p`
Saturation temperature from pressure (IAPWS-IF97-style, 611 Pa – 22 MPa). **Input:** `P_Pa` (required). **Returns:** `T_sat_K`, `T_sat_C`.

### `boiler_psat_from_t`
Saturation pressure from temperature (0.01 – 374°C). **Input:** `T_C` (required). **Returns:** `P_sat_Pa`, `P_sat_kPa`, `P_sat_MPa`.

### `boiler_steam_properties`
Full saturated steam and water properties at given pressure OR temperature. **Input:** `P_Pa` or `T_sat_C` (provide one). **Returns:** `T_sat_C`, `P_sat_Pa`, `P_sat_MPa`, `hf_kJkg`, `hg_kJkg`, `hfg_kJkg`, `sf_kJkgK`, `sg_kJkgK`, `sfg_kJkgK`, `vf_m3kg`, `vg_m3kg`.

### `boiler_superheat_enthalpy`
Superheated steam enthalpy: h_sup ≈ hg(P) + cp·(T_sup − T_sat), cp ≈ 2.05 kJ/kg·K. **Input:** `P_Pa`, `T_sup_C` (required). **Returns:** `h_sup_kJkg`, `T_sat_C`, `superheat_K`.

### `boiler_heat_duty`
Boiler heat duty: Q = m_steam × (h_steam − h_fw) [kW]. **Input:** `m_steam_kgs`, `h_steam_kJkg`, `h_fw_kJkg` (required). **Returns:** `Q_kW`, `Q_kJkg`.

### `boiler_steam_output`
Steam flow from fuel input: m_steam = (Q_fuel × η) / (h_steam − h_fw). **Input:** `Q_fuel_kW`, `efficiency`, `h_steam_kJkg`, `h_fw_kJkg` (required). **Returns:** `m_steam_kgs`, `m_steam_th`.

### `boiler_efficiency_io`
Input-output efficiency: η = (m_steam × (h_steam − h_fw)) / Q_fuel. **Input:** `m_steam_kgs`, `h_steam_kJkg`, `h_fw_kJkg`, `Q_fuel_kW` (required). **Returns:** `efficiency`, `efficiency_pct`, `warnings`.

### `boiler_efficiency_heat_loss`
ASME PTC 4 abbreviated heat-loss method: efficiency = 100% − Σ losses. **Input:** `flue_gas_temp_C` (required); `ambient_temp_C`, `excess_air_pct`, `moisture_fuel_pct`, `radiation_loss_pct`, `unburnt_loss_pct` (optional). **Returns:** all loss components and `efficiency_pct`.

### `boiler_fuel_firing_rate`
Fuel flow: m_fuel = Q_boiler / (η × HHV). **Input:** `Q_boiler_kW`, `efficiency`, `HHV_kJkg` (required). **Returns:** `m_fuel_kgs`, `m_fuel_kgh`, `Q_input_kW`.

### `boiler_combustion_air_flow`
Air flow: m_air = m_fuel × AFR_stoich × (1 + EA/100). **Input:** `m_fuel_kgs` (required); `stoich_air_fuel_ratio` (default 15.6 natural gas), `excess_air_pct` (default 20%). **Returns:** `m_air_stoich_kgs`, `m_air_actual_kgs`, `lambda`.

### `boiler_blowdown_rate`
Continuous blowdown from TDS and cycles of concentration. **Input:** `m_steam_kgs`, `feedwater_TDS_ppm`, `blowdown_TDS_limit_ppm` (required); `cycles_of_concentration` (optional override). **Returns:** `CoC`, `blowdown_fraction`, `m_blowdown_kgs`, `m_blowdown_th`.

### `boiler_blowdown_heat_loss`
Heat lost in blowdown discharge: Q = m_blowdown × (hf_boiler − hf_drain). **Input:** `m_blowdown_kgs`, `P_boiler_Pa` (required); `T_drain_C` (optional, default 40). **Returns:** `Q_loss_kW`.

### `boiler_feedwater_energy_balance`
Overall boiler energy balance including blowdown: Q_absorbed = m_steam·h_steam + m_bd·h_bd − m_fw·h_fw. **Input:** `m_steam_kgs`, `h_steam_kJkg`, `m_blowdown_kgs`, `h_fw_kJkg`, `h_blowdown_kJkg` (required). **Returns:** `m_fw_kgs`, `Q_absorbed_kW`.

### `boiler_deaerator_energy_balance`
Direct-contact deaerator (open feedwater heater) energy balance. **Input:** `m_fw_cold_kgs`, `h_fw_cold_kJkg`, `m_steam_sparging_kgs`, `h_steam_sparging_kJkg` (required); `T_deaerator_C` (default 105). **Returns:** `m_out_kgs`, `h_fw_out_kJkg`.

### `boiler_economizer_energy_balance`
Economizer preheat duty: Q = m_fw × cp × (T_out − T_in). **Input:** `m_fw_kgs`, `T_fw_in_C`, `T_fw_out_C` (required); `cp_fw_kJkgK` (default 4.1868). **Returns:** `Q_econ_kW`, `delta_T_C`, `h_fw_out_kJkg`.

### `boiler_equivalent_evaporation`
Equivalent evaporation and factor of evaporation (from & at 100°C basis, hfg = 2256.9 kJ/kg). **Input:** `m_steam_kgs`, `h_steam_kJkg`, `h_fw_kJkg`, `m_fuel_kgs` (required). **Returns:** `EE_kg_per_kg_fuel`, `factor_of_evaporation`.

### `boiler_horsepower`
Boiler horsepower (1 BHP = 9.81 kW). **Input:** `m_steam_kgs`, `h_steam_kJkg` (required); `h_fw_kJkg` (default 419.06 kJ/kg). **Returns:** `BHP`, `Q_kW`.

### `boiler_pipe_velocity`
Mean steam velocity in circular pipe: v = m × vg / A. Warns >50 m/s or <15 m/s. **Input:** `m_steam_kgs`, `pipe_id_m`, `vg_m3kg` (required). **Returns:** `velocity_ms`, `pipe_area_m2`.

### `boiler_pipe_pressure_drop`
Darcy-Weisbach steam pipe ΔP (Colebrook-White friction factor). **Input:** `m_steam_kgs`, `pipe_id_m`, `pipe_length_m`, `vg_m3kg` (required); `mu_Pa_s`, `roughness_m` (optional). **Returns:** `dP_Pa`, `dP_kPa`, `Reynolds`, `f_darcy`, `velocity_ms`.

### `boiler_flash_steam_fraction`
Flash steam fraction: x = (hf_high − hf_low) / hfg_low. **Input:** `h_condensate_kJkg`, `P_flash_Pa` (required). **Returns:** `flash_fraction`, `T_flash_C`.

### `boiler_condensate_heat_recovery`
Recoverable sensible heat: Q = m × cp × (T_cond − T_drain). **Input:** `m_condensate_kgs`, `T_condensate_C` (required); `T_drain_C` (default 30), `cp_kJkgK` (default 4.1868). **Returns:** `Q_recovered_kW`.

### `boiler_steam_trap_capacity`
Orifice steam trap discharge: m = Cd × A × sqrt(2·rho·dP). **Input:** `dP_bar`, `orifice_dia_mm` (required); `Cd` (default 0.6), `condensate_temp_C` (default 100). **Returns:** `m_condensate_kgs`, `m_condensate_kgh`.

### `boiler_safety_valve_napier`
Napier formula safety valve relief for steam: W = K_Napier × P_abs × A × Ksh. Includes 10% accumulation. **Input:** `set_pressure_barg`, `orifice_area_mm2` (required); `steam_type` (`"saturated"` default or `"superheated"`), `superheat_C` (optional). **Returns:** `W_kgh`, `W_kgs`, `P_abs_bar`, `Ksh`.

---

## Example

```
1. boiler_steam_properties  P_Pa:1000000
   → T_sat_C:179.9  hg_kJkg:2778.1  hf_kJkg:762.8  vg_m3kg:0.1944

2. boiler_heat_duty  m_steam_kgs:5.0  h_steam_kJkg:2778  h_fw_kJkg:420
   → Q_kW: 11790

3. boiler_efficiency_heat_loss  flue_gas_temp_C:200  excess_air_pct:20
   → efficiency_pct: 82.3

4. boiler_safety_valve_napier  set_pressure_barg:9  orifice_area_mm2:500
   → W_kgh: 3300  W_kgs: 0.917
```
