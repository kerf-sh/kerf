# ASCE 7 Wind Load Analysis — LLM Reference

Wind loading on buildings and structures per ASCE/SEI 7-22 Chapters 26–27 and 30.
No OCC dependency. All tools are stateless; no DB write.
Units: Pa (pressures), m/s or mph (wind speed), m (heights).

---

## When to use

Keywords: wind load, ASCE 7, wind pressure, wind speed, velocity pressure, exposure
category, gust factor, MWFRS, main wind force resisting system, components and cladding,
GCp, Kz, Kzt, topographic, base shear, overturning, drift, wind design, building code,
wind hazard, roof pressure, wall pressure, wind directionality, Ke, elevation factor.

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

Velocity pressure exposure coefficient at height z per ASCE 7-22 Table 26.10-1.

**Input:** `z_m` (height above ground, m), `exposure_category` (`"B"` / `"C"` / `"D"`).

**Returns:** `Kz` — coefficient used to scale velocity pressure.

Exposure B: suburban, wooded. C: open terrain. D: flat coastal, lakes.

---

### `wind_Kzt`

Topographic factor Kzt for hills, ridges, and escarpments (ASCE 7-22 §26.8).

**Input:** `K1` (topographic form factor), `K2` (speed-up attenuation with distance), `K3` (speed-up attenuation with height). Kzt = (1 + K1·K2·K3)².

**Returns:** `Kzt` (≥ 1.0). Use Kzt = 1.0 for flat terrain.

---

### `wind_Ke`

Ground elevation factor Ke per ASCE 7-22 §26.9.

**Input:** `z_e_m` (ground elevation above sea level, m).

**Returns:** `Ke` = e^(−0.000119 · z_e) (≤ 1.0).

---

### `wind_qz`

Design velocity pressure qz per ASCE 7-22 Eq. 26.10-1.

SI: qz = 0.613 · Kz · Kzt · Kd · Ke · V² (Pa, V in m/s).
US: qz = 0.00256 · Kz · Kzt · Kd · Ke · V² (psf, V in mph).

**Input:** `Kz`, `Kzt`, `Kd` (wind directionality, 0.85 for buildings), `Ke`, `V` (design wind speed), `units` (`"SI"` or `"US"`, default `"SI"`).

**Returns:** `qz_Pa` (or psf for US).

---

### `wind_G`

Gust-effect factor G for rigid structures (natural frequency ≥ 1 Hz).

**Input:** `exposure_category`, `z_bar_m` (equivalent height, typically 0.6·h). G = 0.925·(1 + 1.7·gq·Iz·Q)/(1 + 1.7·gv·Iz).

**Returns:** `G` (typically 0.85 for open terrain, higher for sheltered sites).

---

### `wind_Gf`

Resonant gust-effect factor Gf for flexible / dynamically sensitive structures (fn < 1 Hz).

**Input:** `exposure_category`, `z_bar_m`, `n1_Hz` (fundamental natural frequency), `beta` (damping ratio, default 0.01), `V_bar_m_s` (mean wind speed at z_bar).

**Returns:** `Gf` (> G for flexible structures).

---

### `wind_mwfrs_wall`

MWFRS windward and leeward external wall pressures per ASCE 7-22 §27.3.

**Input:** `qz_Pa` (velocity pressure at z), `qh_Pa` (velocity pressure at roof height h), `G` (gust factor), `Cp_windward` (windward Cp, default 0.8), `Cp_leeward` (leeward Cp, function of L/B ratio; default −0.5), `GCpi` (internal pressure coefficient, default 0.18 for enclosed).

**Returns:** `p_windward_Pa` (positive = pressure), `p_leeward_Pa` (negative = suction), `p_net_wall_Pa`.

---

### `wind_mwfrs_roof`

MWFRS roof pressures per ASCE 7-22 §27.3 (flat or pitched roof).

**Input:** `qh_Pa`, `G`, `roof_angle_deg`, `building_length_m`, `h_m` (eave height), `leeward` (bool).

**Returns:** `Cp_roof`, `p_roof_Pa`.

---

### `wind_cc_GCp`

External pressure coefficients GCp for components and cladding per ASCE 7-22 §30.

**Input:** `zone` (`"1"`, `"2"`, `"3"` — interior, edge, corner), `effective_area_m2`, `roof_angle_deg` (default 0 = flat roof).

**Returns:** `GCp_pos`, `GCp_neg` (positive and negative design values).

---

### `wind_base_shear`

Total wind base shear and overturning moment for a rectangular building.

**Input:** `pressures` — list of `{z_m, p_Pa, width_m, height_m}` tributary area dicts stacked up the building.

**Returns:** `V_base_N` (base shear), `M_OTM_Nm` (overturning moment about base), `force_distribution` (list per level).

---

### `wind_drift`

Along-wind drift check (simplified cantilever approximation).

**Input:** `V_base_N`, `H_m` (building height), `EI_Nm2` (lateral stiffness — E·I of equivalent cantilever).

**Returns:** `delta_top_m` (tip deflection), `drift_ratio` (δ/H); warns if drift_ratio > 1/500.

---

## Example

```
# 10-storey office, 40 m tall, Exposure C, V=45 m/s, flat site
wind_Ke  z_e_m:100   → Ke: 0.988
wind_Kz  z_m:40  exposure_category:"C"   → Kz: 1.12
wind_Kzt K1:0  K2:0  K3:0               → Kzt: 1.0  (flat terrain)
wind_qz  Kz:1.12  Kzt:1.0  Kd:0.85  Ke:0.988  V:45
  → qz_Pa: 1073

wind_G   exposure_category:"C"  z_bar_m:24
  → G: 0.85

wind_mwfrs_wall  qz_Pa:1073  qh_Pa:1073  G:0.85
  → p_windward_Pa:730  p_leeward_Pa:-457  p_net_wall_Pa:1187

wind_cc_GCp  zone:"3"  effective_area_m2:1.0  roof_angle_deg:0
  → GCp_pos:0.30  GCp_neg:-1.80
```
