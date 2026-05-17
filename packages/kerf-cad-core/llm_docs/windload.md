# ASCE 7-22 Wind Load Analysis

Wind loading on buildings and structures per ASCE/SEI 7-22 Chapters 26–27 and 30.
No OCC dependency. All tools are stateless; no DB write.
Units: Pa (pressures), m/s or mph (wind speed), m (heights).

Authoritative standards:
- **ASCE/SEI 7-22** — *Minimum Design Loads and Associated Criteria for Buildings
  and Other Structures*, Chapters 26 (general wind provisions), 27 (MWFRS
  directional procedure), 30 (C&C low-rise and all heights). All § references
  below are to ASCE 7-22.
- **ASCE 49-21** — *Wind Tunnel Testing for Buildings and Other Structures*
  (for site-specific wind data; not implemented).
- **Davenport (1967)** — gust factor formulation basis for §26.11.

---

## When to use

Keywords: wind load, ASCE 7, wind pressure, wind speed, velocity pressure, exposure
category, gust factor, MWFRS, main wind force resisting system, components and
cladding, GCp, Kz, Kzt, topographic, base shear, overturning, drift, wind design,
building code, wind hazard, roof pressure, wall pressure, wind directionality, Ke,
elevation factor.

---

## Workflow

```
wind_Kz                 → velocity pressure exposure coefficient
wind_Kzt                → topographic amplification factor
wind_Ke                 → ground elevation factor
wind_qz                 → design velocity pressure qz
wind_G / wind_Gf        → gust-effect factor (rigid / flexible)
wind_mwfrs_wall         → MWFRS windward/leeward wall pressures
wind_mwfrs_roof         → MWFRS roof pressures
wind_cc_GCp             → components & cladding GCp coefficients
wind_base_shear         → total base shear and overturning moment
wind_drift              → along-wind drift check
```

---

## Tools

### `wind_Kz`

Velocity pressure exposure coefficient at height z — **ASCE 7-22 Table 26.10-1**.

```
Kz = 2.01·(z/zg)^(2/α)    for z ≥ z_min     [Table 26.10-1 power law]
Kz = 2.01·(z_min/zg)^(2/α) for z < z_min
```
Exposure B: α=7.0, zg=365.8 m; C: α=9.5, zg=274.3 m; D: α=11.5, zg=213.4 m.

**Input:** `z_m` (height above ground, m), `exposure_category` (`"B"` / `"C"` / `"D"`).

**Returns:** `Kz`.

**Standards alignment:** §26.10.1; Table 26.10-1 power-law parameters. Exposure
A (dense urban) is removed from ASCE 7-22. Exposure B: suburban/wooded (z0 ≈ 0.3 m);
C: open terrain (z0 ≈ 0.01 m); D: flat coastal / lakes / open water (z0 ≈ 0.002 m).

---

### `wind_Kzt`

Topographic factor Kzt for hills, ridges, and escarpments — **ASCE 7-22 §26.8**.

```
Kzt = (1 + K1·K2·K3)²                        [§26.8.2, Eq. 26.8-1]
```

**Input:** `K1` (topographic form factor), `K2` (upwind attenuation), `K3`
(vertical speed-up attenuation). Kzt ≥ 1.0.

**Returns:** `Kzt`.

**Standards alignment:** §26.8.2; K1/K2/K3 from Fig. 26.8-1 (hills/ridges and
escarpments); Kzt = 1.0 for flat terrain or for sites outside the topographic
influence zone (x > Lh; z > 2H for escarpments).

---

### `wind_Ke`

Ground elevation factor Ke — **ASCE 7-22 §26.9**.

```
Ke = e^(−0.000119·ze)                        [§26.9.1, Eq. 26.9-1]
```
where ze = site elevation above sea level (m). Ke ≤ 1.0.

**Standards alignment:** §26.9; accounts for reduced air density at elevation
(≥ 900 m sites see meaningful reductions). Ke = 1.0 for sites ≤ 304 m (1000 ft).

---

### `wind_qz`

Design velocity pressure — **ASCE 7-22 Eq. 26.10-1**.

```
SI:  qz = 0.613·Kz·Kzt·Kd·Ke·V²    (Pa, V in m/s)    [Eq. 26.10-1]
US:  qz = 0.00256·Kz·Kzt·Kd·Ke·V²  (psf, V in mph)
```

**Input:** `Kz`, `Kzt`, `Kd` (wind directionality, 0.85 for buildings per
Table 26.6-1), `Ke`, `V` (basic wind speed from §26.5 ASCE hazard maps or
Risk Category wind maps, m/s), `units`.

**Returns:** `qz_Pa` (or psf for US).

**Standards alignment:** §26.10.1, Eq. 26.10-1. V is the 3-second gust wind
speed at 10 m height in open terrain (Exposure C), MRI 700-yr for Risk Category
II buildings. For Risk Category III/IV, use MRI 1700-yr maps.

---

### `wind_G`

Gust-effect factor G for rigid structures (fn ≥ 1 Hz) — **ASCE 7-22 §26.11.4**.

```
G = 0.925·(1 + 1.7·gq·Iz·Q) / (1 + 1.7·gv·Iz)
Iz = c·(33/z̄)^(1/6)  (turbulence intensity at z̄)
Q = 1/√(1 + 0.63·((B+h)/Lz̄)^0.63)
gq = gv = 3.4 (peak factor for rigid structures)
```

**Returns:** `G` (typically 0.85–0.87 for Exposure C).

**Standards alignment:** §26.11.4, Eq. 26.11-6. G = 0.85 may be used as a
conservative simplification for rigid buildings per §26.11.5.

---

### `wind_Gf`

Resonant gust-effect factor Gf for flexible / dynamically sensitive structures
(fn < 1 Hz) — **ASCE 7-22 §26.11.5**.

```
Gf = 0.925·(1 + 1.7·Iz̄·√(gq²Q² + gr²R²)) / (1 + 1.7·gv·Iz̄)
```
where R accounts for resonant response (background + resonant components).

**Input:** `exposure_category`, `z_bar_m`, `n1_Hz` (fundamental natural frequency),
`beta` (damping, default 0.01), `V_bar_m_s` (mean wind speed at z̄).

**Returns:** `Gf` (always > G for flexible structures).

**Standards alignment:** §26.11.5, Eq. 26.11-7. Applicable when fn < 1 Hz
(building height/width > 5 or H > 60 m).

---

### `wind_mwfrs_wall`

MWFRS windward and leeward external wall pressures — **ASCE 7-22 §27.3**.

```
p_windward  = qz·G·Cp_windward − qi·GCpi      [§27.3.1, Eq. 27.3-1]
p_leeward   = qh·G·Cp_leeward − qi·GCpi
```

**Input:** `qz_Pa` (at z), `qh_Pa` (at roof height h), `G`, `Cp_windward`
(default 0.8), `Cp_leeward` (default −0.5 for L/B=1; −0.3 for L/B ≥ 4),
`GCpi` (internal pressure; 0.18 enclosed, −0.18 or +0.55 partially enclosed).

**Returns:** `p_windward_Pa`, `p_leeward_Pa`, `p_net_wall_Pa`.

**Standards alignment:** §27.3.1 (wall Cp from Fig. 27.3-1); GCpi from §26.13
Table 26.13-1. For rectangular buildings: windward Cp = 0.8 (always); leeward
Cp from Table 27.3-1 depends on L/B ratio.

---

### `wind_mwfrs_roof`

MWFRS roof pressures — **ASCE 7-22 §27.3** (flat or pitched roof).

```
p_roof = qh·G·Cp_roof − qi·GCpi
```

**Input:** `qh_Pa`, `G`, `roof_angle_deg`, `building_length_m`, `h_m` (eave
height), `leeward` (bool).

**Returns:** `Cp_roof`, `p_roof_Pa`.

**Standards alignment:** §27.3.2; Cp from Fig. 27.3-1 (roof pressure zones as
function of h/L and roof angle). For flat roofs (θ < 10°): windward upper zone
Cp = −0.9 to −0.3 (h/L-dependent); leeward Cp = −0.5 to −0.3.

---

### `wind_cc_GCp`

External pressure coefficients GCp for components and cladding — **ASCE 7-22
§30** (all-heights method, Chapter 30 Part 1).

**Input:** `zone` (`"1"` interior / `"2"` edge / `"3"` corner), `effective_area_m2`,
`roof_angle_deg` (default 0 = flat roof).

**Returns:** `GCp_pos`, `GCp_neg`.

**Standards alignment:** §30.4 (low-rise) or §30.6 (all heights); Figs. 30.4-1
and 30.4-2A–C (roof zones); Fig. 30.6-1 (wall zones). Zone 3 (corners) has the
largest GCp_neg magnitude (highest suction). Effective area interpolation uses
the log-linear relationships in the ASCE figures.

---

### `wind_base_shear`

Total wind base shear and overturning moment from tributary area pressures.

**Input:** `pressures` — list of `{z_m, p_Pa, width_m, height_m}` dicts stacked
up the building face.

**Returns:** `V_base_N`, `M_OTM_Nm`, `force_distribution` (list per level).

**Standards alignment:** §27.3.1 (integration of MWFRS pressures over tributary
areas); §C27.3 Commentary (base shear = Σ pi·Ai). Torsional effects for
diaphragm flexibility are outside scope — use §27.4 for irregular buildings.

---

### `wind_drift`

Along-wind drift check (simplified cantilever approximation).

```
δ = V_base·H³ / (8·EI)      (uniform cantilever with point load at top)
drift_ratio = δ/H
```

**Input:** `V_base_N`, `H_m`, `EI_Nm2`.

**Returns:** `delta_top_m`, `drift_ratio`; warns if drift_ratio > 1/500.

**Standards alignment:** ASCE 7-22 does not specify a drift limit for wind (unlike
seismic §12.12); the 1/500 warning follows common practice guidance from
AISC Design Guide 3 (serviceability). For serviceability-governing designs,
many codes use H/300 to H/500 for total drift.

---

## Example

```
# 10-storey office, 40 m tall, Exposure C, V=45 m/s, flat site, Risk Cat II
wind_Ke   z_e_m:100       → Ke:0.988  [§26.9]
wind_Kz   z_m:40  exposure_category:"C"  → Kz:1.12  [Table 26.10-1]
wind_Kzt  K1:0  K2:0  K3:0  → Kzt:1.0  (flat terrain)  [§26.8]
wind_qz   Kz:1.12  Kzt:1.0  Kd:0.85  Ke:0.988  V:45
  → qz_Pa:1073  [§26.10.1, Eq. 26.10-1; 0.613×1.12×1.0×0.85×0.988×45²]

wind_G    exposure_category:"C"  z_bar_m:24  → G:0.85  [§26.11.4]

wind_mwfrs_wall  qz_Pa:1073  qh_Pa:1073  G:0.85
  → p_windward_Pa:730  p_leeward_Pa:−457  p_net_wall_Pa:1187  [§27.3.1]

wind_cc_GCp  zone:"3"  effective_area_m2:1.0  roof_angle_deg:0
  → GCp_pos:0.30  GCp_neg:−1.80  [§30 Fig. 30.6-1 corner zone, 1 m² area]
```
