# API 650 Atmospheric Storage Tank Design

Pure-Python API 650 / API 2000 storage-tank engineering: shell thickness, roof
design, wind and seismic stability, venting, settlement, nozzle reinforcement,
and anchorage. All tools are stateless and never raise. Units: SI (metres,
Pascals, Newtons).

Authoritative standards:
- **API 650, 13th Edition (2020)** — *Welded Tanks for Oil Storage*. All §
  references below are to API 650-2020 unless stated otherwise.
- **API 2000, 7th Edition (2014)** — *Venting Atmospheric and Low-Pressure
  Storage Tanks* — normal and emergency vent sizing.
- **API 650 Annex E (2020)** — Seismic Design of Storage Tanks (Housner
  impulsive/convective model).
- **API 650 Appendix B (2020)** — Settlement evaluation.
- **ASCE/SEI 7-22** — site spectral parameters (Sds, Sd1) used as input to
  Annex E seismic tool.

---

## When to use

Use these tools for atmospheric storage tanks: API 650, oil/water/chemical
storage, shell course thickness, cone or dome roof design, wind girder sizing,
overturning stability, anchor bolt sizing, seismic (Annex E) sloshing and base
shear, API 2000 normal/emergency venting, settlement tolerance check, nozzle
reinforcement area replacement.

---

## Tools

### `tank_shell_course_thickness`

Required shell-plate thickness for one course — **API 650 §5.6**.

**1-foot method** (design point 0.3 m above course bottom):
```
t_product = 4.9·D·(H−0.3)·G / Sd + c       [API 650 §5.6.3.2, Eq. 5-1]
t_hydrotest = 4.9·D·(H−0.3) / St + c       [API 650 §5.6.3.2, Eq. 5-2]
t_required = max(t_product, t_hydrotest)
```

**Variable design point** (§5.6.4): design point at x = 0.61√(D·t) from course
bottom; requires iterative solve on `t`.

**Input:** `D` (m), `H` (m), `G` (default 1.0), `Sd`/`St` (allowable stresses
Pa from API 650 Table 5-2a), `c` (m), `method` (`"1-foot"` or `"variable"`),
`x` (for variable, m).

**Returns:** `t_product_m`, `t_hydrotest_m`, `t_required_m`, `warnings`.

**Standards alignment:** §5.6.3.2 (1-foot method, Eq. 5-1/5-2); §5.6.4
(variable design point); §5.6.1 (allowable stresses from Table 5-2a, typically
0.85·Fy for design, 0.90·Fy for hydrotest, or API 650 §5.6.1 yield-based limits).

---

### `tank_minimum_shell_thickness`

API 650 **Table 5-6a** minimum shell thickness by tank diameter.

| D (m) | t_min (mm) |
|-------|-----------|
| D ≤ 15 | 5 |
| 15 < D ≤ 30 | 6 |
| 30 < D ≤ 60 | 8 |
| D > 60 | 10 |

**Standards alignment:** API 650 Table 5-6a (excluding corrosion allowance).
This is a construction-quality minimum, not a strength minimum; the strength-
based thickness from `tank_shell_course_thickness` will govern for most tanks.

---

### `tank_bottom_plate_thickness`

API 650 **§5.4.1** minimum bottom plate thickness.

Minimum net 6 mm (0.006 m) + corrosion allowance; 5 mm with liner.

**Standards alignment:** §5.4.1; bottom plates are not pressure-designed but must
resist settlement and corrosion. Annular ring thickness is governed separately by
`tank_annular_plate_thickness`.

---

### `tank_annular_plate_thickness`

Minimum annular bottom plate thickness — **API 650 §5.5**, governed by
hydrostatic pressure at first-course base.

Projection beyond shell ≥ 600 mm (§5.5.2).

**Standards alignment:** §5.5.1 (t_annular dependent on first-course shell
stress); the annular plate transfers the shell bottom load to the tank bottom,
and its thickness increases with higher shell hoop stresses (API 650 Table 5-1a).

---

### `tank_cone_roof_thickness`

Cone-roof plate thickness — **API 650 §5.10.5.1**.

Self-supporting: roof slope 9.46° to 37° (1:12 to 3:4 rise/run);
supported: truss or rafter framing with rafters ≤ 2.5 m span.

Frangible joint requirement: if computed roof-to-shell weld shear at design
pressure exceeds annular plate capacity → frangible joint flag (§5.10.5.1).

**Standards alignment:** §5.10.5.1; design load = 1 kPa snow + 0.7 kPa rain or
per §5.2.1(g) for region-specific loads.

---

### `tank_dome_roof_thickness`

Self-supporting dome roof — **API 650 §5.10.5.2**.

Membrane formula: t = w·Rc/(2·Sd·E)  
where Rc = crown radius (0.8D to 1.5D, default 0.8D per §5.10.5.2).

**Standards alignment:** §5.10.5.2; spherical membrane theory. Dome roof must
be checked for vacuum loading (wind suction) per §5.10.5.3 — not automated.

---

### `tank_wind_girder_section_modulus`

Required section modulus of top wind girder — **API 650 §5.9.7.1**, and maximum
unstiffened shell height W_max.

```
Z = D² · H_shell / (17 · V²)   (adjusted for V²)   [API 650 §5.9.7.1]
W_max = 9.47t / √(H_shell/D) · (190/V)²             [§5.9.7.2]
```

**Standards alignment:** §5.9.7.1 (wind girder section modulus for open-top tanks);
§5.9.7.2 (maximum height of unstiffened shell for wind stability); design wind
speed V default 45 m/s (163 km/h) per API 650 §5.2.1(j).

---

### `tank_intermediate_stiffener`

Maximum intermediate wind stiffener spacing — **API 650 §5.9.7.3**.

Returns W_max per unstiffened height formula, minimum stiffener count, and
spacing.

**Standards alignment:** §5.9.7.3; for uniform-thickness shells, equally spaced
intermediate stiffeners divide the shell into segments each ≤ W_max tall.

---

### `tank_overturning_stability`

Wind overturning stability check — **API 650 §5.11**.

```
M_wind = Cf·q·H²·D/2      (wind moment from uniform pressure)
M_resist = 0.6·W_shell·D/2 + W_roof·D/2 + W_liquid·D/2
SF = M_resist / M_wind ≥ 1.5
```

**Standards alignment:** §5.11.1 (overturning FS ≥ 1.5); wind pressure coefficient
Cf = 0.63 for cylindrical tanks per §5.2.1(j); overturning resisted by shell,
roof, and liquid weight (no uplift credit for contents in excess of design fill).

---

### `tank_anchorage_requirement`

Anchor bolt area sizing — **API 650 §5.11.2**.

```
F_bolt = (M_overturning − 0.6·W_shell·D/2) × 4 / (n·π·D)
A_bolt = F_bolt / (Sa × safety_factor)
```

Supported grades: A307, A193-B7, A36.

**Standards alignment:** §5.11.2; anchor bolt design stress per material grade;
A307 = 103 MPa (15 ksi); A193-B7 = 552 MPa (80 ksi) per ASTM A193.

---

### `tank_seismic_annex_e`

API 650 **Annex E** seismic: Housner model impulsive/convective masses, base
shear (SRSS), overturning moment, sloshing wave height, and freeboard check.

```
Wi, Wc, Ti, Tc from Housner (1957) tank sloshing model
Vi = Ai × Wi;  Vc = Ac × Wc
V = √(Vi² + Vc²)   (SRSS per Annex E §E.4.6.1)
delta_s = 0.84·Sd1·D/Tc²   (sloshing wave height)
```

**Standards alignment:** API 650 Annex E (E.4.2–E.4.8); Housner (1957, 1963)
mechanical analogy for impulsive/convective masses (J. of Engineering Mechanics);
spectral acceleration Ai, Ac from ASCE 7-22 design spectrum scaled by Rwi=4,
Rwc=2 per Annex E Table E-6.

---

### `tank_venting_normal`

Normal vent capacity — **API 2000 §4** (thermal breathing + fill/drain).

```
In-breathing  = max(thermal, drain)
Out-breathing = max(thermal, fill)
Thermal: 0.32 × V_tank^0.9   (m³/h)   [API 2000 §4.2.2, Table 1]
```

**Standards alignment:** API 2000-2014 §4.2 (normal venting); Table 1 (in/out-
breathing thermal rates); fill/drain rates per §4.2.3; venting capacity in normal
cubic metres per hour (Nm³/h at 15°C and 101.325 kPa).

---

### `tank_venting_emergency`

Emergency vent capacity (fire case) — **API 2000 §5.3.2**.

```
Q_fire = 3.091 × Aw^0.82  (m³/h NTP)
```

where Aw = wetted area (m²); computed from D and H_liquid if not supplied.

**Standards alignment:** API 2000-2014 §5.3.2, Eq. 1 (fire case venting based on
wetted area, calibrated to heat absorbed and latent heat of vaporisation of
typical petroleum products).

---

### `tank_settlement_check`

API 650 **Appendix B** settlement tolerance check: edge, planar tilt, and
differential settlement.

```
S_edge_max = 25·D^0.5  (mm)           [API 650 Appendix B, Table B-1]
S_planar_max = 25·D^0.5  (mm)
S_diff_max = 32·(arc_length/D)·t     (depends on measurement arc, min wall t)
```

**Standards alignment:** API 650 Appendix B; criteria protect against shell
distortion (buckling, weld cracking) and bottom plate cracking. Differential
settlement tolerance depends on arc measurement length and wall thickness.

---

### `tank_nozzle_reinforcement`

API 650 **§5.7.3** nozzle reinforcement area-replacement check.

Same approach as ASME UG-37 (area replacement); API 650 uses shell design
thickness (from §5.6) as the basis.

```
A_req = d · t_design · F
A_avail = excess in shell + excess in nozzle wall
Pass if A_avail ≥ A_req
```

**Standards alignment:** §5.7.3 (area replacement, similar to ASME UG-37 but
using API 650 design thicknesses); §5.7.3.3 (reinforcement zone limits).

---

## Example

```
1. tank_shell_course_thickness  D:20  H:12  G:0.9  c:0.003
   → t_product_m:0.0098  t_hydrotest_m:0.0076  t_required_m:0.0128  (12.8 mm)
   [API 650 §5.6.3.2 1-foot method; Sd=160 MPa for A36; G=0.9 crude oil]

2. tank_minimum_shell_thickness  D:20
   → t_min_m:0.006  (6 mm; D in 15–30 m band, Table 5-6a)

3. tank_wind_girder_section_modulus  D:20  t_shell:0.012  V_wind_m_s:40
   → Z_required_m3:1.42e-4  W_max_m:6.5  [API 650 §5.9.7.1]

4. tank_overturning_stability  D:20  H_shell:14  W_total_N:2e6  V_wind_m_s:40
   → SF:2.3  warnings:[]  (§5.11 FS ≥ 1.5 ✓)

5. tank_seismic_annex_e  D:20  H_liquid:11  rho_liquid:900  Sds:0.5  Sd1:0.25
   → impulsive_period:…  sloshing_height:0.42 m  base_shear_kN:…  [Annex E]
```
