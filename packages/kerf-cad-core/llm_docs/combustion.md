# Combustion & Fuels Engineering

Pure-Python combustion engineering tools for stoichiometry, flue-gas composition,
adiabatic flame temperature, HHV/LHV conversion, Siegert efficiency, dew-point,
CO2 max, and fuel thermal power. No OCC dependency. All tools are stateless and
never raise.

---

## When to use

Use when the user asks about: combustion, air-fuel ratio, AFR, stoichiometric,
equivalence ratio, phi, lambda, excess air, flue gas, combustion products, CO2,
adiabatic flame temperature, heat of combustion, HHV, LHV, higher heating value,
lower heating value, combustion efficiency, Siegert method, flue gas dew point,
acid dew point, CO2 max, fuel power, thermal power, specific fuel consumption,
methane, propane, natural gas, burner, boiler efficiency.

---

## Tools

### `combustion_stoich_afr`

Stoichiometric air-fuel ratio (mass and molar) for a CxHyOzNwSv fuel.

**Input:**
- `C` (required), `H` (required) — carbon and hydrogen atom counts in fuel formula
- `O`, `N`, `S` — optional heteroatom counts (default 0)
- `fuel_name` — optional label

**Output:** `AFR_mass`, `AFR_molar`, `n_O2_stoich`, `MW_fuel`. Reference: CH₄ AFR_mass ≈ 17.2; C₃H₈ ≈ 15.6; gasoline ≈ 14.7

---

### `combustion_equivalence_ratio`

Convert between equivalence ratio φ, lambda λ, and excess-air %.

**Input:** supply ONE of: (`afr_actual` + `afr_stoich`), `phi`, `excess_air_pct`, or `lambda_`

**Output:** `phi`, `lambda_`, `excess_air_pct`, `mixture` (rich/lean/stoichiometric)

---

### `combustion_product_composition`

Complete-combustion product-gas composition (wet and dry mole fractions, ppm).

**Input:**
- `C` (required), `H` (required); optional `O`, `N`, `S`, `excess_air_pct`, `fuel_name`

**Output:** wet and dry mole fractions of CO₂, H₂O, O₂, N₂, SO₂; warns for rich mixtures (incomplete combustion risk)

---

### `combustion_adiabatic_flame_temp`

Adiabatic flame temperature via iterative constant-pressure energy balance.

**Input:**
- `C` (required), `H` (required); optional `O`, `N`, `S`, `T_reactants` (K, default 298.15), `excess_air_pct`, `LHV_MJ_kg`, `MW_fuel`

**Output:** `T_adiabatic_K`, `T_adiabatic_C`. Reference values (stoichiometric): CH₄ ≈ 2230 K; C₃H₈ ≈ 2267 K. Warns if T > 3000 K (dissociation overestimate)

---

### `combustion_hhv_to_lhv`

Convert HHV ↔ LHV using water condensation latent heat (h_fg = 2.442 MJ/kg).

**Input:**
- `HHV_MJ_kg` (required), `C` (required), `H` (required); optional `O`, `N`, `S`, `MW_fuel`, `direction` (`"hhv_to_lhv"` default or `"lhv_to_hhv"`)

**Output:** `LHV_MJ_kg` (or `HHV_MJ_kg`), `delta_MJ_kg`, `H2O_yield_kg_per_kg_fuel`

---

### `combustion_efficiency`

Combustion efficiency and Siegert flue-gas heat loss (EN 15502 / VDI 2067).

**Input:**
- `T_flue_C` (required), `T_ambient_C` (required)
- `CO2_dry_pct` (preferred) or `O2_dry_pct` + `CO2_max_pct`
- `fuel` — `"natural_gas"` (default), `"methane"`, `"oil"`, `"coal"`, `"propane"`

**Output:** `q_A_pct` (Siegert heat loss %), `efficiency_pct`

---

### `combustion_flue_gas_dew_point`

Flue-gas water dew-point temperature from H₂O mole fraction (Antoine equation).

**Input:** `H2O_wet_frac` OR `H2O_wet_pct` (at least one required); optional `p_total_Pa` (default 101325)

**Output:** `dew_point_C`, `dew_point_K`, `p_H2O_Pa`

---

### `combustion_co2_max`

Maximum (stoichiometric, dry) CO₂ percentage — the Bacharach / Siegert reference point.

**Input:** `C` (required), `H` (required); optional `O`, `N`, `S`

**Output:** `CO2_max_pct`. Reference: CH₄ ≈ 11.7%; C₃H₈ ≈ 13.7%; gasoline ≈ 15.1%

---

### `combustion_fuel_power`

Fuel energy → thermal power and specific fuel consumption (SFC).

**Input:** supply (`mass_flow_kg_s` OR `vol_flow_m3_s` + `density_kg_m3`) AND (`LHV_MJ_kg` or `HHV_MJ_kg`); or `target_power_W` to back-calculate mass flow; optional `eta_combustion` (default 1.0)

**Output:** `P_thermal_kW`, `P_thermal_W`, `SFC_kg_kWh`, `mass_flow_kg_s`

---

## Example

```
1. combustion_stoich_afr  C:1  H:4          (methane CH₄)
   → AFR_mass:17.2  n_O2_stoich:2.0

2. combustion_product_composition  C:1  H:4  excess_air_pct:10
   → CO2_dry_pct:10.64  O2_dry_pct:1.91

3. combustion_efficiency
     T_flue_C:180  T_ambient_C:20  CO2_dry_pct:9.5  fuel:"natural_gas"
   → q_A_pct:6.1  efficiency_pct:93.9
```
