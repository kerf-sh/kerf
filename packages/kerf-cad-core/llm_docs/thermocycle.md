# Thermodynamic Cycle Analysis — LLM Reference

Air-standard and vapour-cycle thermodynamics per Cengel & Boles. No OCC dependency.
All tools are stateless; no DB write. Units: K, Pa, J/kg, dimensionless efficiency.

---

## When to use

Keywords: thermodynamic cycle, Otto cycle, Diesel cycle, Brayton cycle, Rankine cycle,
Carnot efficiency, isentropic, isothermal, isobaric, isochoric, polytropic, heat engine,
COP, refrigeration, heat pump, compression ratio, thermal efficiency, work output,
steam cycle, gas turbine, regeneration, intercooling.

---

## Workflow

```
# Process-level analysis
thermo_isentropic_relations / thermo_isothermal_process / ... → state properties

# Cycle-level analysis
thermo_otto_cycle / thermo_diesel_cycle / thermo_dual_cycle     → SI engine
thermo_brayton_cycle                                            → gas turbine
thermo_rankine_cycle_ideal                                      → steam plant
thermo_carnot_efficiency                                        → ideal upper bound
```

---

## Tools

### `thermo_isentropic_relations`

Isentropic T/p/v relations for ideal gas state change.

**Input:** `T1_K`, `p1_Pa` (or `v1_m3_kg`), `ratio` (compression or expansion), `k` (specific heat ratio, default 1.4).

**Returns:** `T2_K`, `p2_Pa`, `v2_m3_kg`.

---

### `thermo_isothermal_process`

Isothermal (constant temperature) ideal-gas process.

**Input:** `T_K`, `p1_Pa`, `v1_m3_kg`, `p2_Pa` (or `v2_m3_kg`).

**Returns:** final state properties, `work_J_kg`, `heat_J_kg`.

---

### `thermo_isobaric_process`

Isobaric (constant pressure) ideal-gas process.

**Input:** `p_Pa`, `T1_K`, `T2_K`, `cp_J_kgK` (default 1005).

**Returns:** `v1_m3_kg`, `v2_m3_kg`, `work_J_kg` = p·Δv, `heat_J_kg` = cp·ΔT.

---

### `thermo_isochoric_process`

Isochoric (constant volume) ideal-gas process.

**Input:** `v_m3_kg`, `T1_K`, `T2_K`, `cv_J_kgK` (default 717.86).

**Returns:** `p1_Pa`, `p2_Pa`, `work_J_kg` (= 0), `heat_J_kg` = cv·ΔT.

---

### `thermo_isentropic_process`

Isentropic compression or expansion.

**Input:** `T1_K`, `p1_Pa`, `p2_Pa`, `k` (default 1.4), `cp`, `cv`.

**Returns:** `T2_K`, `v1_m3_kg`, `v2_m3_kg`, `work_J_kg`.

---

### `thermo_polytropic_process`

Polytropic process p·vⁿ = const.

**Input:** `p1_Pa`, `v1_m3_kg`, `n` (polytropic index), `p2_Pa` (or `v2_m3_kg`).

**Returns:** `T1_K`, `T2_K`, `p2_Pa`, `v2_m3_kg`, `work_J_kg`.

---

### `thermo_carnot_efficiency`

Carnot heat-engine efficiency (theoretical maximum).

**Input:** `T_cold_K`, `T_hot_K`.

**Returns:** `eta_carnot` = 1 − T_cold/T_hot; warns if T_cold ≥ T_hot.

---

### `thermo_carnot_cop_refrigeration`

Reverse-Carnot refrigeration COP (theoretical maximum).

**Input:** `T_cold_K`, `T_hot_K`.

**Returns:** `COP_ref` = T_cold / (T_hot − T_cold).

---

### `thermo_carnot_cop_heat_pump`

Reverse-Carnot heat-pump COP (theoretical maximum).

**Input:** `T_cold_K`, `T_hot_K`.

**Returns:** `COP_hp` = T_hot / (T_hot − T_cold).

---

### `thermo_otto_cycle`

Air-standard Otto cycle (ideal spark-ignition petrol engine).

**Input:** `r` (compression ratio, > 1), `T1_K` (BDC inlet temperature), `T3_K` (peak temperature after heat addition), `k` (default 1.4), `cp`, `cv`.

**Returns:** `eta_otto`, `T2_K`, `T4_K`, `w_net_J_kg`, `q_in_J_kg`, `q_out_J_kg`; warns if η exceeds Carnot limit.

---

### `thermo_diesel_cycle`

Air-standard Diesel cycle (ideal compression-ignition engine).

**Input:** `r` (compression ratio), `r_c` (cutoff ratio v3/v2), `T1_K`, `k`, `cp`, `cv`.

**Returns:** `eta_diesel`, state temperatures, `w_net_J_kg`, `q_in_J_kg`.

---

### `thermo_dual_cycle`

Air-standard Dual (mixed) cycle (combines constant-volume and constant-pressure heat addition).

**Input:** `r`, `r_p` (pressure ratio p3/p2), `r_c` (cutoff ratio), `T1_K`, `k`, `cp`, `cv`.

**Returns:** `eta_dual`, all state temperatures, `w_net_J_kg`.

---

### `thermo_brayton_cycle`

Brayton cycle (gas turbine) with optional regeneration.

**Input:** `r_p` (pressure ratio), `T1_K` (compressor inlet), `T3_K` (turbine inlet), `k`, `eta_c` (compressor isentropic efficiency, default 1.0), `eta_t` (turbine isentropic efficiency, default 1.0), `regenerator` (bool, default false), `eta_regen` (regenerator effectiveness, default 0.8).

**Returns:** `eta_brayton`, `w_net_J_kg`, `w_compressor_J_kg`, `w_turbine_J_kg`, `back_work_ratio`.

---

### `thermo_rankine_cycle_ideal`

Simplified ideal Rankine (steam) cycle using polynomial steam-table approximations.

**Input:** `p_boiler_Pa` (boiler pressure), `p_condenser_Pa` (condenser pressure), `T_superheat_K` (optional superheat).

**Returns:** `eta_rankine`, `w_net_J_kg`, `q_in_J_kg`, `q_out_J_kg`; warns if superheat temperature below saturation.

---

### `thermo_refrigeration_cop`

Refrigeration or heat-pump COP from measured or calculated heat flows.

**Input:** `Q_L_J` (heat removed from cold space), `W_in_J` (compressor work input).

**Returns:** `COP_ref` = Q_L / W_in, `COP_hp` = (Q_L + W_in) / W_in.

---

## Example

```
# Ideal Otto cycle at r=9, T1=300 K, T3=2200 K
thermo_otto_cycle  r:9  T1_K:300  T3_K:2200
  → eta_otto: 0.585  T2_K: 728  T4_K: 908  w_net_J_kg: 883 000

# Brayton gas turbine r_p=10, T1=300 K, T3=1400 K with 85% component efficiency
thermo_brayton_cycle  r_p:10  T1_K:300  T3_K:1400  eta_c:0.85  eta_t:0.88
  → eta_brayton: 0.374  w_net_J_kg: 285 000  back_work_ratio: 0.62
```
