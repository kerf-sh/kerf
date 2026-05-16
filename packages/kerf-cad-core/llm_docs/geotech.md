# Geotechnical and Foundation Engineering

Pure-Python geotechnical calculations: bearing capacity, settlement, lateral earth
pressure, retaining wall stability, slope stability, and pile capacity. No OCC dependency.
All tools stateless. Units: kN, m, kPa. References: Das "Principles of Geotechnical
Engineering" 9th ed.; Terzaghi (1943); Meyerhof (1951); Rankine; Coulomb; API RP 2GEO.

---

## When to use

Use these tools when the user asks about:
- bearing capacity, allowable bearing pressure, foundation design
- shallow foundation, strip footing, square footing, circular footing
- settlement, consolidation settlement, immediate settlement, Terzaghi, Cc, void ratio
- lateral earth pressure, active pressure, passive pressure, Rankine, Coulomb
- retaining wall, gravity wall, cantilever wall, overturning, sliding, factor of safety
- slope stability, infinite slope, factor of safety slope, saturated slope, hw/H
- pile capacity, pile axial load, skin friction, end bearing, alpha method
- geotechnical, soil mechanics, foundation analysis

---

## Tools

### `geotech_bearing_capacity`

Ultimate and allowable bearing capacity using Terzaghi (1943) bearing-capacity factors
with shape factors for strip, square, or circular footings.

```
Strip:    q_ult = c·Nc + q·Nq + 0.5·γ·B·Nγ
Square:   q_ult = 1.3·c·Nc + q·Nq + 0.4·γ·B·Nγ
Circular: q_ult = 1.3·c·Nc + q·Nq + 0.3·γ·B·Nγ
q_allow  = q_ult / FS
```

**Input:**
- `c` (required) — cohesion (kPa, >= 0)
- `phi_deg` (required) — friction angle (°, 0–45)
- `gamma` (required) — soil unit weight (kN/m³)
- `Df` (required) — foundation depth (m)
- `B` (required) — foundation width (m)
- `foundation_type` — `strip` (default), `square`, or `circular`
- `FS` — factor of safety (default 3.0)
- `surcharge` — additional surcharge at foundation level (kPa, default 0)

**Returns:** `Nc`, `Nq`, `Ngamma`, `q_ult_kPa`, `q_allow_kPa`, `warnings`.

---

### `geotech_settlement`

Foundation settlement — consolidation (Terzaghi 1D) or immediate (elastic Boussinesq).

```
Consolidation: Sc = (Cc / (1+e0)) × H × log10(σ'v / σ'v0)
Immediate:     Si ≈ q·B·(1−ν²) / Es
```

**Input:**
- `sigma_v` (required) — final effective vertical stress or bearing pressure (kPa)
- `Cc` (required) — compression index or elastic modulus Es (kPa)
- `e0` (required) — initial void ratio or Poisson ratio ν
- `H` (required) — compressible layer thickness or footing width (m)
- `sigma_v0` — initial effective stress (kPa; default 0.5 × sigma_v)
- `settlement_type` — `consolidation` (default) or `immediate`

**Returns:** `settlement_m`, `settlement_mm`, `warnings`.

---

### `geotech_lateral_earth_pressure`

Rankine or Coulomb Ka/Kp and resultant active/passive forces per unit wall length,
including surcharge and water-table effects.

**Input:**
- `gamma` (required) — soil unit weight (kN/m³)
- `H` (required) — retained wall height (m)
- `phi_deg` (required) — friction angle (°)
- `method` — `rankine` (default) or `coulomb`
- `c` — cohesion (kPa, default 0)
- `delta_deg` — wall friction angle δ (°, Coulomb only, default 0)
- `surcharge` — uniform backfill surcharge (kPa, default 0)
- `hw` — water-table depth from top (m, default 0 = fully dry)

**Returns:** `Ka`, `Kp`, `Pa_kN_m`, `Pp_kN_m`, `Pa_z_m` (centroid depth), `warnings`.

---

### `geotech_retaining_wall`

Stability check of a gravity or cantilever retaining wall: overturning, sliding, bearing.

**Input:**
- `Fa` (required) — active resultant force per unit length (kN/m)
- `Fp` (required) — passive resultant force per unit length (kN/m)
- `W_wall` (required) — total vertical weight of wall + retained soil (kN/m)
- `x_W` (required) — distance from toe to resultant vertical force (m)
- `B_base` (required) — base width (m)
- `Df`, `c`, `phi_deg`, `gamma` (all required) — foundation conditions
- `FS_req_ot` — required FS overturning (default 2.0)
- `FS_req_sl` — required FS sliding (default 1.5)
- `FS_req_bc` — required FS bearing (default 3.0)

**Returns:** `FS_overturning`, `FS_sliding`, `FS_bearing`, `ok_*` booleans, `eccentricity_m`, `warnings`.

---

### `geotech_slope_stability`

Simplified infinite-slope factor of safety (dry, partially saturated, or fully saturated).

```
Dry:          FS = c/(γ·H·sin β·cos β) + tan φ / tan β
Saturated:    FS = c/(γ·H·sin β·cos β) + (1 − m·γw/γ)·tan φ / tan β
```

**Input:**
- `gamma`, `c`, `phi_deg`, `H`, `beta_deg` (all required)
- `hw_ratio` — hw/H, 0=dry (default), 1.0=fully saturated
- `FS_req` — required factor of safety (default 1.5)

**Returns:** `FS`, `adequate` (bool), `warnings`.

---

### `geotech_pile_capacity`

Axial pile capacity: alpha-method skin friction + end bearing.

```
Qs = α × fs × perimeter × L
Qp = qp × A_tip
Q_ult = Qs + Qp
Q_allow = Q_ult / FS
```

**Input:**
- `perimeter` (required) — pile perimeter (m)
- `area_tip` (required) — pile tip cross-sectional area (m²)
- `unit_skin_friction` (required) — average unit skin friction fs (kPa)
- `unit_end_bearing` (required) — unit end-bearing qp (kPa)
- `pile_length` (required) — total pile length (m)
- `alpha` — adhesion factor α (default 1.0; typical 0.4–0.8 for driven piles in soft clay)
- `FS` — factor of safety (default 3.0)

**Returns:** `Qs_kN`, `Qp_kN`, `Q_ult_kN`, `Q_allow_kN`, `warnings`.

---

## Example

```
1. geotech_bearing_capacity  c:10  phi_deg:30  gamma:18  Df:1.5  B:2.0  foundation_type:"square"
   → q_ult_kPa:1243  q_allow_kPa:414  warnings:[]

2. geotech_lateral_earth_pressure  gamma:18  H:4.0  phi_deg:30  method:"rankine"
   → Ka:0.333  Kp:3.0  Pa_kN_m:48.0

3. geotech_slope_stability  gamma:19  c:5  phi_deg:28  H:3.0  beta_deg:25  hw_ratio:0.5
   → FS:1.62  adequate:true
```
