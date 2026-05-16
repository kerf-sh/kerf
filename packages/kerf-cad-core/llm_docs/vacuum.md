# Vacuum System Design

Pure-Python vacuum-system engineering: Knudsen number and flow regime classification, conductance of orifices and tubes (all regimes), series/parallel conductance networks, effective pumping speed, pump-down time (volume + outgassing model), ultimate pressure, gas throughput, outgassing load, leak-rate measurement, rate-of-rise prediction, mean free path, monolayer formation time, and roughing/high-vacuum stage matching. No OCC dependency. All tools are stateless and never raise. References: O'Hanlon (3rd ed.), Jousten (2016).

---

## When to use

Use these tools for vacuum system design and analysis: determine flow regime (viscous/transitional/molecular), size vacuum conductance of orifices and tubes, combine conductances in series or parallel, compute effective pump speed at chamber, estimate pump-down time with outgassing, calculate ultimate pressure from gas load and pump speed, compute gas throughput and outgassing load, measure system leak rate from rate-of-rise, predict pressure rise during isolation test, mean free path vs pressure, monolayer contamination time, match roughing pump to turbomolecular or diffusion pump.

---

## Tools

### `vacuum_flow_regime`

Classify vacuum flow regime from Knudsen number: Kn < 0.01 = viscous; 0.01–0.5 = transitional; > 0.5 = molecular. **Input:** `pressure_Pa`, `diameter_m` (required); `temperature_K` (optional, default 293.15). **Returns:** `Kn`, `mean_free_path_m`, `regime`.

---

### `vacuum_conductance_orifice`

Conductance of a thin circular orifice (molecular, viscous, or transitional interpolation). **Input:** `diameter_m`, `pressure_Pa` (required); `temperature_K`, `regime` (`auto` default, or `molecular`/`viscous`/`transitional`). **Returns:** `C_m3s`, `regime_used`, `Kn`, `area_m2`.

---

### `vacuum_conductance_tube`

Conductance of a long circular tube (L >> D). Molecular: C = (π/12)·v_avg·D³/L; Viscous: C = π·D⁴·P_avg/(128·η·L); transitional interpolated. **Input:** `diameter_m`, `length_m`, `pressure_Pa` (required); `temperature_K`, `regime` (optional). **Returns:** `C_m3s`, `C_mol_m3s`, `C_vis_m3s`, `Kn`, `regime_used`. Warns if L/D < 3.

---

### `vacuum_conductance_series`

Equivalent conductance in series: 1/C_total = Σ (1/C_i). **Input:** `conductances` (list of m³/s, required). **Returns:** `C_total_m3s`.

---

### `vacuum_conductance_parallel`

Equivalent conductance in parallel: C_total = Σ C_i. **Input:** `conductances` (list of m³/s, required). **Returns:** `C_total_m3s`.

---

### `vacuum_effective_speed`

Effective pumping speed at the chamber: 1/S_eff = 1/S_pump + 1/C. **Input:** `S_pump_m3s`, `C_m3s` (required). **Returns:** `S_eff_m3s`, `S_eff_frac`. Warns if S_eff < 50% of S_pump (conductance bottleneck).

---

### `vacuum_pump_down_time`

Two-phase pump-down time: Phase 1 volume-limited (V/S·ln(P_start/P_cross)), Phase 2 outgassing-dominated (V/S·ln((P_cross−P_ult)/(P_target−P_ult))). **Input:** `volume_m3`, `S_eff_m3s`, `P_start_Pa`, `P_target_Pa` (required); `outgassing_load_Pa_m3s`, `surface_area_m2`, `outgassing_rate_Pa_m3s_m2` (optional). **Returns:** `t_phase1_s`, `t_phase2_s`, `t_total_s`, `P_ult_Pa`, `P_crossover_Pa`.

---

### `vacuum_ultimate_pressure`

Ultimate (base) pressure: P_ult = Q_gas / S_pump. **Input:** `Q_gas_Pa_m3s`, `S_pump_m3s` (required). **Returns:** `P_ult_Pa`. Warns if > 1×10⁻³ Pa for HV applications.

---

### `vacuum_gas_throughput`

Gas throughput Q = S · P (Pa·m³/s). **Input:** `S_m3s`, `P_Pa` (required). **Returns:** `Q_Pa_m3s`.

---

### `vacuum_outgassing_rate`

Total outgassing load: Q_out = q_specific × A. **Input:** `area_m2`, `specific_rate_Pa_m3s_m2` (required). **Returns:** `Q_outgassing_Pa_m3s`. Typical rates: SS unbaked ~1×10⁻⁶, SS baked ~1×10⁻⁸, Viton O-ring ~1×10⁻⁵.

---

### `vacuum_leak_rate_spec`

Leak rate from rate-of-rise test: Q_leak = V·(dP/dt). Returns measured leak rate, helium-equivalent, and leak class (ultra_fine/fine/gross/very_gross). **Input:** `P_test_Pa`, `volume_m3`, `dp_dt_Pa_s` (required); `test_gas` (`air` default, `nitrogen`, or `helium`). **Returns:** `leak_rate_Pa_m3s`, `helium_equiv_Pa_m3s`, `leak_class`.

---

### `vacuum_rate_of_rise`

Predict pressure rise during isolation: P(t) = P_initial + (Q/V)·t. **Input:** `Q_leak_Pa_m3s`, `volume_m3`, `time_s`, `P_initial_Pa` (required). **Returns:** `dP_dt_Pa_s`, `P_final_Pa`, `delta_P_Pa`.

---

### `vacuum_mean_free_path`

Mean free path: λ = k_B·T / (√2·π·d_mol²·P). **Input:** `pressure_Pa` (required); `temperature_K` (optional). **Returns:** `mfp_m`, `v_avg_m_s`, `n_density`.

---

### `vacuum_monolayer_time`

Time to form one monolayer of adsorbate: τ = n_s / (Φ·s). At 1×10⁻⁶ Pa ≈ 1 s; at 1×10⁻¹⁰ Pa > 10 h. **Input:** `pressure_Pa` (required); `temperature_K`, `sticking_coefficient` (optional). **Returns:** `tau_s`, `flux_m2s`.

---

### `vacuum_pump_stage_match`

Multi-stage vacuum system matching: roughing pump-down to crossover, high-vac pump-down to ultimate, crossover pressure validation. **Input:** `roughing_speed_m3s`, `roughing_base_Pa`, `highvac_speed_m3s`, `highvac_base_Pa`, `volume_m3` (required); `crossover_P_Pa` (optional, auto-selected if omitted). **Returns:** `crossover_Pa`, `t_roughing_s`, `t_highvac_s`, `t_total_s`, `crossover_ok`, `warnings`.

---

## Example

```
1. vacuum_flow_regime  pressure_Pa:0.01  diameter_m:0.05
   → Kn: 0.66  regime:"molecular"

2. vacuum_conductance_tube  diameter_m:0.05  length_m:0.5  pressure_Pa:0.01
   → C_m3s: 0.012  regime_used:"molecular"

3. vacuum_effective_speed  S_pump_m3s:0.1  C_m3s:0.012
   → S_eff_m3s: 0.011  S_eff_frac:0.11  (conductance bottleneck warning)

4. vacuum_pump_down_time
     volume_m3:0.05  S_eff_m3s:0.011
     P_start_Pa:101325  P_target_Pa:1e-5
   → t_phase1_s: 54  t_phase2_s: 290  t_total_s: 344
```
