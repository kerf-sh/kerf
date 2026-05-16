# Applied Aerodynamics — LLM Reference

ICAO ISA atmosphere, thin-airfoil theory, finite-wing aerodynamics, and aircraft
performance (Anderson). No OCC dependency. All tools are stateless; no DB write.
Units: metres, m/s, Pa, kg/m³, dimensionless coefficients.

---

## When to use

Keywords: aerodynamics, airfoil, wing, lift, drag, thrust, Mach number, dynamic pressure,
ISA atmosphere, altitude, standard atmosphere, CL, CD, L/D ratio, induced drag, thin airfoil,
finite wing, aspect ratio, Prandtl, angle of attack, stall speed, rate of climb, propeller,
thrust, Breguet range, endurance, level flight, glide, aircraft performance, subsonic,
transonic.

---

## Workflow

```
aero_atmosphere           → ρ, p, T, a at altitude
  → aero_dynamic_pressure → q = ½ρV²
  → aero_mach             → Mach number
aero_thin_airfoil         → Cl for symmetric/cambered airfoil section
aero_finite_wing          → CL corrected for aspect ratio (Prandtl lifting-line)
aero_drag_buildup         → total CD0 + CDi; L/D; best-glide CL
aero_level_flight         → required thrust, power, stall speed
aero_climb_rate           → rate of climb from excess power
aero_propeller            → actuator-disc thrust and ideal efficiency
aero_breguet              → cruise range and endurance
```

---

## Tools

### `aero_atmosphere`

ICAO Standard Atmosphere properties at a given altitude.

**Input:** `altitude_m` (geopotential altitude, 0–20 000 m).

**Returns:** `T_K`, `p_Pa`, `rho_kg_m3`, `a_m_s` (speed of sound); covers troposphere and isothermal lower stratosphere.

---

### `aero_dynamic_pressure`

Dynamic pressure q = ½ρV².

**Input:** `rho_kg_m3`, `V_m_s` (airspeed).

**Returns:** `q_Pa`.

---

### `aero_mach`

Mach number and transonic flag.

**Input:** `V_m_s`, `a_m_s` (speed of sound from `aero_atmosphere`).

**Returns:** `Mach`, `transonic` (true if 0.8 ≤ M ≤ 1.2), `supersonic`.

---

### `aero_thin_airfoil`

Thin-airfoil theory: section lift and moment coefficients.

**Input:** `alpha_deg` (angle of attack), `camber_ratio` (max camber / chord, default 0 for symmetric), `camber_location` (x/c of max camber, default 0.4).

**Returns:** `Cl` = 2π(α + 2·camber_ratio), `Cm_c4` (pitching moment about c/4 per unit span). Valid for small angles and thin sections; pre-stall only.

---

### `aero_finite_wing`

Finite-wing CL and corrected lift-curve slope via Prandtl lifting-line theory.

**Input:** `alpha_deg`, `AR` (aspect ratio b²/S), `e` (span efficiency factor, default 1.0), `camber_ratio` (default 0), `camber_location` (default 0.4).

**Returns:** `CL`, `dCL_dalpha` (rad⁻¹), `alpha_induced_deg`.

---

### `aero_drag_buildup`

Total aircraft drag coefficient, L/D ratio, and best-glide CL.

**Input:** `CL`, `AR`, `e` (Oswald efficiency, default 0.8), `CD0` (zero-lift drag coefficient), `CL_max` (optional stall limit).

**Returns:** `CDi` (induced drag), `CD_total`, `LD_ratio`, `best_glide_CL`, `best_glide_LD`.

---

### `aero_level_flight`

Required thrust, shaft power, and stall speed for steady level flight.

**Input:** `W_N` (weight), `S_m2` (wing area), `rho_kg_m3`, `V_m_s`, `CD_total`, `CL`, `CL_max`.

**Returns:** `T_required_N`, `P_required_W`, `V_stall_m_s`, `load_factor`.

---

### `aero_climb_rate`

Rate of climb from excess power.

**Input:** `P_available_W` (engine/propeller shaft power), `P_required_W` (from `aero_level_flight`), `W_N`.

**Returns:** `ROC_m_s` (rate of climb), `excess_power_W`, `climb_angle_deg`.

---

### `aero_propeller`

Actuator-disc propeller thrust and ideal propulsive efficiency.

**Input:** `P_shaft_W` (shaft power), `rho_kg_m3`, `D_m` (propeller diameter), `V_inf_m_s` (free-stream speed).

**Returns:** `T_N` (ideal thrust), `eta_propulsive` (ideal efficiency), `induced_velocity_m_s`.

---

### `aero_breguet`

Breguet range and endurance for a propeller-driven aircraft.

**Input:** `eta_p` (propeller efficiency, 0–1), `c_specific` (specific fuel consumption, kg/(N·s)), `CL`, `CD`, `W_initial_N`, `W_final_N`.

**Returns:** `range_m`, `range_km`, `endurance_s`, `endurance_h`.

---

## Example

```
# Cruise performance at 3000 m, 60 m/s
aero_atmosphere  altitude_m:3000
  → rho_kg_m3:0.909  T_K:268.7  a_m_s:328.6

aero_dynamic_pressure  rho_kg_m3:0.909  V_m_s:60
  → q_Pa: 1636

aero_mach  V_m_s:60  a_m_s:328.6
  → Mach:0.183  transonic:false

aero_finite_wing  alpha_deg:4  AR:8  e:0.85  camber_ratio:0.04
  → CL:0.72  dCL_dalpha:4.68

aero_drag_buildup  CL:0.72  AR:8  e:0.85  CD0:0.025
  → CD_total:0.0485  LD_ratio:14.8  best_glide_CL:0.447

aero_level_flight  W_N:12000  S_m2:18  rho_kg_m3:0.909  V_m_s:60
               CD_total:0.0485  CL:0.72  CL_max:1.6
  → T_required_N:810  V_stall_m_s:38.2

aero_breguet  eta_p:0.82  c_specific:8e-8  CL:0.72  CD:0.0485
              W_initial_N:12000  W_final_N:9500
  → range_km: 1842  endurance_h: 8.5
```
