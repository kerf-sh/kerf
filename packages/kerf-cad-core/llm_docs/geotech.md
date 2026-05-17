# Geotechnical and Foundation Engineering

Pure-Python geotechnical calculations: bearing capacity, settlement, lateral earth
pressure, retaining wall stability, slope stability, and pile capacity. No OCC
dependency. All tools stateless. Units: kN, m, kPa.

Authoritative standards:
- **Terzaghi (1943)** — *Theoretical Soil Mechanics*, bearing-capacity factors
  Nc, Nq, Nγ and shape factors for strip/square/circular footings.
- **Meyerhof (1951)** — general bearing capacity with inclination and depth factors
  (referenced for context; Terzaghi shape factors are used in this implementation).
- **Rankine (1857)** — active/passive earth pressure coefficients Ka/Kp for
  cohesionless soils (horizontal backfill, frictionless wall).
- **Coulomb (1776)** — wedge-equilibrium Ka for soils with wall friction δ.
- **Mohr-Coulomb failure criterion** — shear strength τ = c + σ·tan φ; used in
  bearing capacity, slope stability, and retaining wall checks.
- **Das, *Principles of Geotechnical Engineering***, 9th ed. — implementation
  reference for all formulas.
- **API RP 2GEO (2011)** — offshore piles (alpha method reference).

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

Ultimate and allowable bearing capacity — Terzaghi (1943) bearing-capacity factors
with shape factors for strip, square, or circular footings.

```
Strip:    q_ult = c·Nc + q·Nq + 0.5·γ·B·Nγ
Square:   q_ult = 1.3·c·Nc + q·Nq + 0.4·γ·B·Nγ
Circular: q_ult = 1.3·c·Nc + q·Nq + 0.3·γ·B·Nγ
q_allow   = q_ult / FS
```

where q = γ·Df + surcharge, and Nc, Nq, Nγ from Terzaghi's tables as functions
of φ.

**Input:**
- `c` (required) — cohesion (kPa, ≥ 0)
- `phi_deg` (required) — friction angle (°, 0–45)
- `gamma` (required) — soil unit weight (kN/m³)
- `Df` (required) — foundation depth (m)
- `B` (required) — foundation width (m)
- `foundation_type` — `strip` (default), `square`, or `circular`
- `FS` — factor of safety (default 3.0)
- `surcharge` — additional surcharge at foundation level (kPa, default 0)

**Returns:** `Nc`, `Nq`, `Ngamma`, `q_ult_kPa`, `q_allow_kPa`, `warnings`.

**Standards alignment:**
- Shape factors: Terzaghi (1943) Table 4.1; strip = 1.0/1.0/0.5, square =
  1.3/1.0/0.4, circular = 1.3/1.0/0.3 (Das 9th ed. §3.4).
- N factors: Reissner (Nq), Prandtl (Nc = (Nq−1)·cot φ), Meyerhof/Vesic Nγ
  approximation (Das §3.4, Table 3.2).
- FS = 3.0 is the typical geotechnical safety factor for sustained loads
  (Das §3.14; IBC 2018 §1806.1).

---

### `geotech_settlement`

Foundation settlement — consolidation (Terzaghi 1D) or immediate (elastic
Boussinesq).

```
Consolidation: Sc = (Cc / (1+e0)) × H × log10(σ'v / σ'v0)    [Terzaghi 1D]
Immediate:     Si ≈ q·B·(1−ν²) / Es                          [Boussinesq]
```

**Input:**
- `sigma_v` — final effective vertical stress (kPa)
- `Cc` — compression index (consolidation) or Es elastic modulus (kPa) for immediate
- `e0` — initial void ratio (consolidation) or Poisson ratio ν (immediate)
- `H` — compressible layer thickness (m)
- `sigma_v0` — initial effective stress (kPa; default 0.5×sigma_v)
- `settlement_type` — `consolidation` (default) or `immediate`

**Returns:** `settlement_m`, `settlement_mm`, `warnings`.

**Standards alignment:**
- Consolidation: Terzaghi (1943) one-dimensional consolidation theory
  (Das §11.9, Eq. 11.34): Sc = Cc·H/(1+e0)·log10(σ'v/σ'v0). Valid for
  normally consolidated clay (σ'v0 ≈ σ'pc). For over-consolidated clay,
  split using Cs (swelling index) below the preconsolidation pressure.
- Immediate: Boussinesq elastic approximation for flexible uniformly loaded
  footing (Das §5.10). More accurate methods (e.g. Schmertmann 1970) are
  outside scope.

---

### `geotech_lateral_earth_pressure`

Rankine or Coulomb Ka/Kp and resultant active/passive forces per unit wall
length, including surcharge and water-table effects.

**Rankine (horizontal backfill, frictionless wall):**
```
Ka = tan²(45 − φ/2)           [Rankine 1857]
Kp = tan²(45 + φ/2)
```

**Coulomb (wall friction δ, sloped backfill β):**
```
Ka = sin²(θ+φ) / [sin²θ · sin(θ−δ) · (1 + √(sin(φ+δ)·sin(φ−β)/(sin(θ−δ)·sin(θ+β))))²]
```

With water table at depth hw:
- Effective unit weight γ' = γ − γw below water table for effective stress.
- Hydrostatic water pressure added separately.

**Input:**
- `gamma`, `H`, `phi_deg` (all required)
- `method` — `rankine` (default) or `coulomb`
- `c`, `delta_deg` (Coulomb only), `surcharge`, `hw`

**Returns:** `Ka`, `Kp`, `Pa_kN_m`, `Pp_kN_m`, `Pa_z_m` (centroid depth),
`warnings`.

**Standards alignment:**
- Rankine: Das §7.3 (cohesionless), §7.7 (with cohesion Ka−c component).
- Coulomb: Das §7.5, Eq. 7.28. Coulomb Kp formula not implemented (Coulomb Kp
  is inaccurate for δ > φ/2 — use Rankine Kp or log-spiral method for passive).
- AASHTO LRFD Bridge Design §11.5.5 references Coulomb for retaining walls.

---

### `geotech_retaining_wall`

Stability check of a gravity or cantilever retaining wall: overturning, sliding,
bearing.

```
FS_ot = M_resist / M_driving    ≥ FS_req_ot (default 2.0)
FS_sl = (W·tan φ + c·B) / Fa   ≥ FS_req_sl (default 1.5)
FS_bc = q_allow / q_toe_bearing ≥ FS_req_bc (default 3.0)
```

**Input:**
- `Fa`, `Fp` — active/passive resultant forces (kN/m)
- `W_wall`, `x_W`, `B_base`, `Df`, `c`, `phi_deg`, `gamma`
- `FS_req_ot`, `FS_req_sl`, `FS_req_bc`

**Returns:** `FS_overturning`, `FS_sliding`, `FS_bearing`, `ok_*` booleans,
`eccentricity_m`, `warnings`.

**Standards alignment:**
- FS requirements: Das §8.3–§8.5 (overturning 2.0, sliding 1.5, bearing 3.0).
- AASHTO LRFD §11.6.3.3 overturning (EV load group); sliding §11.6.3.6.
- Eccentricity limit: e ≤ B/6 for no tension in base (Das §8.4); flagged in
  warnings when exceeded.

---

### `geotech_slope_stability`

Simplified infinite-slope factor of safety.

```
Dry/moist:   FS = c/(γ·H·sin β·cos β) + tan φ / tan β
Saturated:   FS = c/(γ·H·sin β·cos β) + (1 − hw/H·γw/γ)·tan φ / tan β
```

**Input:**
- `gamma`, `c`, `phi_deg`, `H`, `beta_deg` (all required)
- `hw_ratio` — hw/H, 0 = dry (default), 1.0 = fully saturated
- `FS_req` — required factor of safety (default 1.5)

**Returns:** `FS`, `adequate` (bool), `warnings`.

**Standards alignment:**
- Infinite-slope model: Das §15.4, Eq. 15.14–15.16. Valid for shallow failure
  planes (depth/length < 0.1). For rotational or deep-seated failures use
  Bishop's method or Spencer's method (outside scope).
- FS ≥ 1.5 required for permanent slopes; FS ≥ 1.3 for temporary cuts —
  USACE EM 1110-2-1902.

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
- `perimeter`, `area_tip`, `unit_skin_friction`, `unit_end_bearing`,
  `pile_length` (all required)
- `alpha` — adhesion factor α (default 1.0; typical 0.4–0.8 for driven piles
  in soft clay — see API RP 2GEO Table 1)
- `FS` — factor of safety (default 3.0)

**Returns:** `Qs_kN`, `Qp_kN`, `Q_ult_kN`, `Q_allow_kN`, `warnings`.

**Standards alignment:**
- Alpha method for cohesive soils: Tomlinson (1957); API RP 2GEO §6.4.2;
  α depends on undrained shear strength su: α ≈ 1.0 for su < 25 kPa, decreasing
  to 0.5 for su > 75 kPa (Das §11.5).
- Beta method (not implemented) for sand piles: API RP 2GEO §6.4.3.
- End bearing in clay: qp = 9·su (Das §11.7); in sand: qp = 0.5·pa·Nq (Das
  §11.6) — provide these directly as `unit_end_bearing`.
- FS = 3.0 (Das §11.12; AASHTO §10.5.3 for static load tests may permit 2.0).

---

## Example

```
1. geotech_bearing_capacity  c:10  phi_deg:30  gamma:18  Df:1.5  B:2.0
                              foundation_type:"square"
   → Nc:30.14  Nq:18.40  Ngamma:22.40
   → q_ult_kPa:1243  q_allow_kPa:414  (FS=3.0, Terzaghi 1943 square shape factors)

2. geotech_lateral_earth_pressure  gamma:18  H:4.0  phi_deg:30  method:"rankine"
   → Ka:0.333  Kp:3.0  Pa_kN_m:48.0  Pa_z_m:1.33 m from base
   (Rankine Ka = tan²(45−15°) = 0.333)

3. geotech_slope_stability  gamma:19  c:5  phi_deg:28  H:3.0  beta_deg:25
                             hw_ratio:0.5
   → FS:1.62  adequate:true  (Das §15.4 saturated infinite slope)
```
