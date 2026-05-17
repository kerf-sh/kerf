# HVAC Duct Sizing

Pure-Python HVAC duct design calculations per ASHRAE Fundamentals Chapter 21.
No OCC dependency. All tools are stateless — they compute and return results;
no DB write. Units: US customary (CFM, fpm, in. w.g., BTU/h, °F, inches) with
Pa conversions where applicable.

Authoritative standards:
- **ASHRAE Handbook — Fundamentals (2021), Chapter 21** — "Duct Design" —
  equal-friction method, velocity-reduction method, Darcy-Weisbach friction,
  duct fitting loss coefficients, fan laws. All § references below are to ASHRAE
  Fundamentals 2021 Ch. 21 unless noted.
- **Huebscher (1948)** — equivalent diameter formula for rectangular ducts:
  De = 1.30·(ab)^0.625 / (a+b)^0.25 — ASHRAE Fundamentals Ch. 21 Table 1.
- **Darcy-Weisbach** — friction pressure loss (ASHRAE Ch. 21 Eq. 1).
- **ASHRAE Handbook — HVAC Systems and Equipment (2020), Chapter 20** — fan
  selection and affinity laws.
- **SMACNA HVAC Duct Construction Standards (2006)** — duct pressure classes and
  construction; fitting C coefficients.
- **ASHRAE 62.1-2022** — *Ventilation and Acceptable Indoor Air Quality* — minimum
  outdoor air rates (input to load calculation, not implemented here).

---

## When to use

Trigger on: HVAC duct, duct sizing, airflow CFM, round duct, rectangular duct,
equivalent diameter, duct friction loss, duct pressure drop, duct fitting,
equal friction method, velocity reduction method, static pressure, fan law,
fan affinity law, supply air, return air, sensible load, BTU/h cooling, heating
load airflow, duct design, ASHRAE duct.

---

## Tools

### `hvac_cfm_from_sensible_load`

Required airflow from a sensible heating or cooling load.

```
CFM = Q_btuh / (1.08 × ΔT_F)      [ASHRAE Fundamentals §18.2]
```
where 1.08 = ρ·cp·60 min/hr ≈ 0.075 lb/ft³ × 0.24 BTU/lb·°F × 60.

**Key inputs:** `Q_btuh` (BTU/h), `delta_T_F` (supply-air temperature
differential, °F; typical 20°F cooling, 50°F heating).

**Returns:** `cfm`.

**Standards alignment:** ASHRAE Fundamentals Ch. 18 Eq. (11); the factor 1.08
(sometimes 1.10 for fan heat) applies to standard air at sea level, 70°F dry-
bulb. For high-altitude or high-humidity applications, adjust ρ·cp.

---

### `hvac_round_duct_diameter`

Round duct diameter from airflow and target velocity.

```
D = √(4·Q / (π·V))              (D in ft, Q in ft³/s, V in ft/s)
   → converted to inches
```

**Key inputs:** `cfm`, `velocity_fpm`.

**Returns:** `diameter_in`.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 velocity guidelines:
- Main trunk: 1000–2000 fpm (commercial); 600–900 fpm (residential).
- Branch ducts: 600–1500 fpm.
- Velocity > 1500 fpm in branches: warns per ASHRAE Ch. 21 §2.3 (noise risk).

---

### `hvac_rect_equiv_diameter`

Huebscher (1948) equivalent diameter for a rectangular duct.

```
De = 1.30·(a·b)^0.625 / (a+b)^0.25    (inches)   [ASHRAE Ch. 21, Table 1]
```

**Key inputs:** `a_in` (width), `b_in` (height).

**Returns:** `D_e_in`.

**Standards alignment:** Huebscher (1948), ASHRAE Ch. 21 Table 1; De is the
diameter of a round duct with the same friction rate at the same velocity. Aspect
ratio > 4:1 triggers a warning (ASHRAE recommends ≤ 4:1 for efficiency; SMACNA
≤ 6:1 construction maximum).

---

### `hvac_duct_friction_loss`

Darcy-Weisbach friction pressure loss for a straight round duct.

```
ΔP_friction = f·(L/D)·(ρV²/2)         [Darcy-Weisbach; ASHRAE Ch. 21 Eq. 1]
f from Colebrook-White: 1/√f = −2·log(ε/(3.7D) + 2.51/(Re·√f))
Initial f from Swamee-Jain approximation.
Friction rate = ΔP / L × 100   (in. w.g. per 100 ft)
```

**Key inputs:** `cfm`, `diameter_in`, `length_ft`. Optional: `roughness_ft`
(default 0.00015 ft for galvanised steel sheet metal).

**Returns:** `loss_in_wg`, `loss_Pa`, `friction_rate_in_per_100ft`, `velocity_fpm`,
`Re`.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 Eq. 1 (Darcy-Weisbach);
roughness ε = 0.00015 ft = 0.046 mm for galvanised steel (ASHRAE Ch. 21 Table 2;
SMACNA Table 1-1). Recommended design friction rate: 0.08–0.10 in. w.g./100 ft
(equal-friction method per ASHRAE Ch. 21 §3.2).

---

### `hvac_duct_fitting_loss`

Dynamic pressure loss for a single duct fitting — local (minor) loss coefficient.

```
ΔP_fitting = C·(ρV²/2)                [ASHRAE Ch. 21 §2.2, Eq. 2]
```

**Key inputs:** `cfm`, `diameter_in`, `C` (loss coefficient, dimensionless).

**Returns:** `loss_in_wg`, `loss_Pa`, `velocity_fpm`, `dynamic_pressure_in_wg`.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 §2.2 and ASHRAE Handbook
fitting tables; SMACNA HVAC Duct Design (2015) — C values for elbows (0.22 for
r/D=1.5 mitre elbow with vanes; 0.15 for r/D=2.5 smooth elbow), tees, transitions,
and entries. Provide C from ASHRAE Ch. 21 Table 3 or SMACNA tables.

---

### `hvac_size_equal_friction`

Size a round duct by the equal-friction method.

Finds the diameter that produces the target friction rate (in. w.g./100 ft) at
the given airflow.

**Key inputs:** `cfm`, `friction_rate_in_per_100ft` (target; 0.08–0.10 for
low-velocity; 0.10–0.15 medium-velocity). Optional: `roughness_ft`.

**Returns:** `diameter_in`, `velocity_fpm`, `friction_rate_confirmation`.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 §3.2 (equal-friction method);
most common design approach for commercial buildings; maintains consistent
pressure loss per unit length to self-balance the system.

---

### `hvac_size_velocity_reduction`

Size a duct system by the velocity-reduction method.

**Key inputs:** `cfm_list` (CFM per section), `velocity_fpm_list` (target velocity
per section; decreasing from trunk to branch).

**Returns:** list of `{diameter_in, velocity_fpm}` per section.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 §3.3 (velocity-reduction
method); trunk velocities 1200–1800 fpm decreasing to 600–900 fpm at terminals;
used in residential and low-velocity commercial systems.

---

### `hvac_branch_static_pressure`

Total static pressure for a duct branch path from fan to terminal.

**Key inputs:** `sections` — list of `{cfm, diameter_in, length_ft, fittings:[{C}]}`.

**Returns:** `total_static_pressure_in_wg`, `total_static_pressure_Pa`,
per-section friction + fitting loss breakdown.

**Standards alignment:** ASHRAE Fundamentals Ch. 21 §4 (total pressure method);
the path with the highest total static pressure is the "index circuit" — the fan
must provide at least that total static pressure. Used in fan selection per ASHRAE
Systems and Equipment Ch. 20.

---

### `hvac_fan_law_scale`

Scale fan performance to a new airflow using affinity laws.

```
CFM₂/CFM₁ = N₂/N₁
SP₂/SP₁   = (N₂/N₁)²
BHP₂/BHP₁ = (N₂/N₁)³
```

**Key inputs:** `cfm1`, `sp1` (in. w.g.), `bhp1` (BHP), `cfm2`.

**Returns:** `cfm2`, `sp2_in_wg`, `bhp2`.

**Standards alignment:** ASHRAE Systems and Equipment (2020) Ch. 20 §2.3
(fan affinity laws); valid for the same fan, same duct system, varying speed.
Warns when speed ratio > 1.2 or < 0.5 (affinity laws less accurate outside
this range per ASHRAE commentary).

---

## Example

**User:** "I have a 36 000 BTU/h sensible cooling load with a 20°F ΔT. Size the
main trunk duct at 1200 fpm and find its friction loss over 50 feet."

```
1. hvac_cfm_from_sensible_load  Q_btuh:36000  delta_T_F:20
   → CFM:1667   [ASHRAE Ch. 18; 36000/(1.08×20)]

2. hvac_round_duct_diameter  cfm:1667  velocity_fpm:1200
   → diameter_in:16.0   [D = √(4×1667/(π×1200×1/60)) → 16 in]

3. hvac_duct_friction_loss  cfm:1667  diameter_in:16  length_ft:50
   → friction_rate:0.092 in/100 ft  loss_in_wg:0.046  loss_Pa:11.4
   [Darcy-Weisbach, Re=~2.2×10⁵, f=0.016, within equal-friction target 0.08–0.10]

4. hvac_size_equal_friction  cfm:1667  friction_rate_in_per_100ft:0.10
   → diameter_in:15.5   (confirm vs step 2 — consistent)
```
