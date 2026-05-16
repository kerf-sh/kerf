# Hydraulic Transient Analysis (Water Hammer)

Pure-Python hydraulic transient / water-hammer analysis tools. No OCC dependency. All tools are
stateless. References: Wylie & Streeter (1993), Chaudhry (2014).

---

## When to use

Water hammer, hydraulic transients, pressure surge, valve closure, Joukowsky, rapid closure,
slow closure, pipe period, wave speed, wave celerity, pressure wave, Method of Characteristics MOC,
pump trip, power failure, rundown, check valve slam, air vessel, surge protection, surge tank,
oscillation, relief valve, column separation, cavitation, pipeline pressure transient.

---

## Tools

### `waterhammer_wave_speed`

Pressure-wave celerity a (m/s) accounting for fluid compressibility, pipe wall elasticity, axial
restraint, and entrained gas (Wylie & Streeter Table 2.1).

**Input:** `K_fluid` (Pa, required), `rho` (kg/m³, required), `D` (m, required),
`e` (wall thickness m, required), `E_pipe` (Pa, required),
`restraint` (`'anchored-both'`/`'anchored-up'`/`'expansion-joint'`), `alpha_gas`, `P_abs`

**Returns:** `a_m_s`, `K_eff`, `c1`, warnings if a outside 100–1600 m/s

---

### `waterhammer_joukowsky`

Joukowsky head rise for valve closure, with automatic regime selection:
- Rapid (t_close ≤ T_pipe): ΔH = a·V0/g
- Slow (t_close > T_pipe): ΔH = 2·L·V0/(g·t_close)

**Input:** `V0` (m/s, required), `a` (m/s, required), `L` (m, required), `t_close` (s, required),
`rho`, `P_vapor_Pa`, `H0`, `pipe_rating_m` (optional)

**Returns:** `T_pipe_s`, `regime`, `dH_m`, `H_max_m`, flags for column separation and overpressure

---

### `waterhammer_moc`

Method-of-Characteristics (MOC) single-pipe transient solver (Wylie & Streeter §3.2).
Returns head and velocity envelopes (max/min vs position) over the simulation period.

**BCs:** upstream constant-head reservoir; downstream `'valve'` (closure law) or `'dead-end'`.
Closure laws: `'linear'` or `'parabolic'`.

**Input:** `L`, `D`, `a`, `V0`, `H_res`, `f` (Darcy friction), `n_reaches`, `t_total` (all required),
`closure_law`, `t_close`, `downstream_bc`, `P_vapor_Pa`, `rho`, `pipe_rating_m`

**Returns:** `H_max_envelope`, `H_min_envelope`, `V_max_envelope`, position grid, warnings

---

### `waterhammer_safe_closure_time`

Minimum safe valve-closure time to limit surge head rise.
t_close_min = 2·L·V0 / (g·dH_allowable).

**Input:** `V0` (required), `a` (required), `L` (required), `H0` (required),
`dH_allowable` (m, required)

**Returns:** `t_close_min_s`, `T_pipe_s`, `dH_joukowsky_m`, warning if still in rapid-closure regime

---

### `waterhammer_pump_trip`

Simplified pump-trip (power failure) transient: rundown time, Joukowsky head drop,
check-valve slam, column separation risk.

**Input:** `H_ss` (m, required), `V0` (required), `a` (required), `L` (required),
`WR2` (kg·m², required), `n_rated` (rpm, required), `P_rated_W` (required),
`rho`, `P_vapor_Pa`

**Returns:** `t_rundown_s`, `dH_trip_m`, `H_min_m`, `column_separation_risk`

---

### `waterhammer_air_vessel`

Minimum air vessel volume for surge protection (Chaudhry §13.3).
Vol_min = a·L·V0·A_pipe / (2·g·dH_allowable).

**Input:** `V0` (required), `A_pipe` (m², required), `a` (required), `L` (required),
`H_res` (required), `dH_allowable` (required), `rho`, `polytropic_n` (default 1.2)

**Returns:** `vol_min_m3`, `vol_recommended_m3` (1.5× safety), `P_air_initial_Pa`

---

### `waterhammer_surge_tank`

Surge tank oscillation period and amplitude (Wylie & Streeter §8.1, undamped).
T_osc = 2π·√(L·A_tank / (g·A_pipe)); z_max = V0·√(L·A_tank / (g·A_pipe)).

**Input:** `L` (m, required), `A_pipe` (m², required), `A_tank` (m², required),
`H0` (m, required), `V0` (required), `rho`

**Returns:** `T_osc_s`, `z_max_m`, warning if z_max > H0

---

### `waterhammer_relief_valve`

Relief valve discharge flow rate. Q = Cv·√(dP_psi) (converted to m³/s).
Valve opens when H_operating > H_set.

**Input:** `H_set` (m, required), `H_operating` (m, required), `Cv` (GPM/√psi, required),
`rho`, `P_atm_Pa`

**Returns:** `Q_m3s`, `dH_m`, `valve_open` (bool)

---

## Example

```
1. waterhammer_wave_speed
     K_fluid:2.07e9  rho:998  D:0.6  e:0.012  E_pipe:200e9
   → a_m_s: 1180

2. waterhammer_joukowsky  V0:3.5  a:1180  L:800  t_close:0.5
   → T_pipe_s: 1.36  regime:"rapid"  dH_m: 421

3. waterhammer_safe_closure_time  V0:3.5  a:1180  L:800  H0:60  dH_allowable:30
   → t_close_min_s: 18.7

4. waterhammer_moc
     L:800  D:0.6  a:1180  V0:3.5  H_res:80
     f:0.015  n_reaches:8  t_total:3.0
   → H_max_envelope: [...]  H_min_envelope: [...]
```
