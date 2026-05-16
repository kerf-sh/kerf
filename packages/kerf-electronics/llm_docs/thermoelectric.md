# Thermoelectric Module Design (TEC & TEG)

Peltier cooler (TEC) and Seebeck generator (TEG) design: figure of merit,
operating point, optimal current, maximum ΔT, couple count, heatsink
coupling, multistage cascade, TEG output power, efficiency, array sizing,
and fill factor.

## When to use

Peltier cooler, TEC, thermoelectric cooler, cooling module, COP,
coefficient of performance, Seebeck, TEG, thermoelectric generator,
waste-heat recovery, ZT, figure of merit, cold-side temperature, hot-side
temperature, heatsink, thermal resistance, multistage TEC, cascade cooler,
laser cooling, detector cooling, CPU cooling, thermoelectric array,
fill factor, pellet geometry.

## Tools

### `tec_figure_of_merit`
Z and ZT from Seebeck coefficient, electrical resistance, and thermal conductance.
Z = α²/(R·K); ZT = Z·T_mean. Inputs: `alpha`, `resistance`, `thermal_conductance`, optional `t_mean`.
Returns `Z`, `ZT`.

### `tec_operating_point`
Steady-state Qc, Qh, input power, and COP at a given drive current and temperatures.
Inputs: `alpha`, `resistance`, `thermal_conductance`, `current`, `tc`, `th`.
Returns `Qc`, `Qh`, `P_input`, `COP`, `delta_T`.

### `tec_optimal_current`
Optimal drive currents: I_max_Qc (maximises cooling) and I_max_COP (maximises COP).
Inputs: `alpha`, `resistance`, `thermal_conductance`, `tc`, `th`.
Returns `I_max_Qc`, `Qc_at_I_max_Qc`, `I_max_COP`, `COP_max`, `Z`, `ZT_mean`.

### `tec_delta_t_max`
Maximum achievable ΔT at zero heat load: ΔT_max = ½·Z·Tc².
Inputs: `alpha`, `resistance`, `thermal_conductance`, `tc`.
Returns `delta_T_max`, `Th_max`, `Z`.

### `tec_couples_required`
Minimum couples N for a target cold-side heat-pumping rate Qc_target.
Scales Qc linearly with N; returns N = ceil(Qc_target / Qc_per_couple).
Inputs: per-couple `alpha`, `resistance`, `thermal_conductance`, `current`, `tc`, `th`, `Qc_target`.
Returns `N`, `Qc_per_couple`, `Qc_total`, `Qh_total`, `P_total`, `COP`.

### `tec_heatsink_coupled`
Closed-loop Th solve for a TEC coupled to a heatsink via fixed-point iteration.
Equilibrium: Th = T_ambient + Rθ·Qh(Th).
Inputs: `alpha`, `resistance`, `thermal_conductance`, `current`, `tc`, `t_ambient`, `rtheta`.
Returns `Th`, `Qc`, `Qh`, `P_input`, `COP`, `converged`, `iterations`.

### `tec_multistage`
Cascade (multistage) TEC design for ΔT exceeding a single module's limit.
Input: `stages` list (each: `alpha`, `resistance`, `thermal_conductance`, `current`),
`t_cold_target`, `t_hot_ambient`.
Returns `stages_results`, `total_delta_T`, `Tc_final`, `Th_final`.

### `teg_output`
TEG open-circuit voltage, matched-load power, and arbitrary-load operating point.
Inputs: `alpha`, `resistance`, `n_couples`, `tc`, `th`; optional `r_load`.
Returns `Voc`, `Ri`, `Im`, `Pm`, `I_load`, `V_load`, `P_load`, `eta_carnot`.

### `teg_efficiency`
TEG maximum efficiency and optimal load resistance (Ioffe/Goldsmid formula).
Inputs: `alpha`, `resistance`, `thermal_conductance`, `tc`, `th`.
Returns `eta_max`, `eta_carnot`, `eta_ratio`, `Z`, `ZT_mean`, `M`, `R_opt_per_couple`.

### `teg_array`
TEG module array output: Ns modules in series × Np modules in parallel.
Inputs: `alpha`, `resistance`, `n_couples`, `tc`, `th`, `n_series`, `n_parallel`.
Returns `Varray`, `Iarray`, `Parray`, `n_total_modules`, `Voc_module`, `Pm_module`.

### `teg_fill_factor`
TEG module fill factor: FF = total pellet area / module footprint.
Inputs: `pellet_area_mm2`, `pellet_height_mm`, `n_couples`, `module_footprint_mm2`.
Returns `fill_factor`, `total_pellet_area_mm2`, `n_legs`.

## Example

Find the operating point of a TEC module at I = 2 A, Tc = 260 K, Th = 300 K:

```json
{
  "tool": "tec_operating_point",
  "alpha": 0.05,
  "resistance": 2.0,
  "thermal_conductance": 0.5,
  "current": 2.0,
  "tc": 260,
  "th": 300
}
```
