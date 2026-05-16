# Welding Process Engineering

Pure-Python weld process engineering tools. No OCC dependency. Covers arc heat input,
carbon equivalent, preheat, cooling time, weld metal volume, deposition, distortion, and
interpass checks. All tools stateless. References: AWS D1.1/D1.1M:2020; IIW Doc. IXJ-123-85;
Lincoln Electric Procedure Handbook 14th ed.; Radaj (1992).

---

## When to use

Use these tools when the user asks about:
- welding, arc welding, SMAW, GMAW, FCAW, SAW, GTAW, MIG, TIG, stick welding
- heat input, arc energy, kJ/mm
- carbon equivalent, CE, IIW formula, weldability
- preheat temperature, preheating, hydrogen cracking, cold cracking
- cooling time, t8/5, HAZ, martensite, grain growth
- fillet weld volume, fillet leg, weld throat
- groove weld, V-groove, groove volume, weld cross-section
- deposition rate, deposition time, welding time estimate
- electrode consumption, wire consumption, spatter, deposition efficiency
- number of passes, multi-pass weld
- angular distortion, transverse distortion, warping, Okerblom
- longitudinal distortion, bowing, cambering
- interpass temperature, interpass check, AWS D1.1

---

## Tools

### `weld_arc_heat_input`

Arc heat input per unit weld length.

`HI = η × V × I / (1000 × v)`  (kJ/mm)

**Input:**
- `eta` (required) — thermal efficiency (SMAW≈0.80, GMAW≈0.85, SAW≈0.99, GTAW≈0.60)
- `V` (required) — arc voltage (V)
- `I` (required) — welding current (A)
- `v` (required) — travel speed (mm/s)

**Returns:** `HI_kJ_mm`; flags HI > 3.5 kJ/mm.

---

### `weld_carbon_equivalent_iiw`

IIW carbon equivalent for preheat assessment.

`CE = C + Mn/6 + (Cr + Mo + V)/5 + (Cu + Ni)/15`  (all in wt%)

**Input:**
- `C`, `Mn` (required); `Si`, `Cr`, `Mo`, `V`, `Cu`, `Ni` (optional, default 0)

**Returns:** `CE`; flags CE > 0.45 (preheat needed) and CE > 0.70 (high cracking risk).

---

### `weld_preheat_temperature`

Minimum preheat temperature per AWS D1.1 / Yurioka approach.

Two methods combined conservatively:
- Method A (AWS D1.1): `T_p = 350√(CE) − 25` °C
- Method B (Yurioka Pcm): `T_p = 1440·Pcm − 392` °C

With thickness (+10°C/mm above 25 mm) and heat-input (−5°C/kJ·mm above 1.0) corrections.

**Input:**
- `CE` (required) — IIW carbon equivalent
- `t_mm` (required) — base metal thickness (mm)
- `HI_kJ_mm` (required) — arc heat input (kJ/mm)

**Returns:** `T_preheat_C` (clamped to 0), `warnings`.

---

### `weld_cooling_time_t85`

Weld cooling time t8/5 (800 °C → 500 °C) using Rykalin simplified formula.

- Butt weld (3D heat flow, thick plate)
- Fillet weld (2D heat flow, thin plate)

**Input:**
- `HI_kJ_mm` (required), `T_preheat_C` (required), `t_mm` (required)
- `joint_type` — `butt` (default, 3D) or `fillet` (2D)

**Returns:** `t85_s`; flags short t8/5 (martensite risk) and long t8/5 (grain growth).

---

### `weld_fillet_volume`

Weld metal volume for an equal-leg fillet weld.

`Area = leg² / 2`,  `Volume = Area × length`,  `Throat = leg / √2`

**Input:**
- `leg_mm` (required) — fillet leg length (mm)
- `length_mm` (required) — weld run length (mm)

**Returns:** `volume_mm3`, `area_mm2`, `throat_mm`.

---

### `weld_groove_volume`

Weld metal volume for a V-groove weld (trapezoidal cross-section).

`area = (w_top + w_root) / 2 × (depth − root_face)`;  `volume = area × length`

**Input:**
- `depth_mm`, `width_top_mm`, `width_root_mm`, `length_mm` (all required)
- `included_angle_deg` (default 60°), `root_face_mm` (default 2), `root_gap_mm` (default 3)

**Returns:** `volume_mm3`, `area_mm2`, `width_top_mm`.

---

### `weld_deposition_time`

Deposition time from weld metal volume and deposition rate.

`time_s = (volume_mm3 × density_kg_mm3 / deposition_rate_kg_h) × 3600`

**Input:**
- `volume_mm3` (required), `deposition_rate_kg_h` (required)
- `density_kg_mm3` (default 7.85e-6)

**Returns:** `time_s`, `time_hr`, `mass_kg`.

---

### `weld_electrode_consumption`

Gross electrode/wire mass including spatter and stub losses.

`electrode_mass_kg = deposit_mass_kg / deposition_efficiency`

**Input:**
- `volume_mm3` (required)
- `density_kg_mm3` (default 7.85e-6)
- `deposition_efficiency` — fraction deposited (default 0.65 SMAW; GMAW≈0.95, SAW≈0.99)

**Returns:** `electrode_mass_kg`, `deposit_mass_kg`.

---

### `weld_number_of_passes`

Estimated number of passes to fill a groove.

`n_passes = ceil(groove_area_mm2 / pass_area_mm2)`

**Input:**
- `groove_area_mm2` (required) — total groove cross-section area (mm²)
- `pass_area_mm2` (required) — average pass area (mm²); typical SMAW 3.2 mm ≈ 30–50 mm²

**Returns:** `n_passes`; flags > 30 passes.

---

### `weld_angular_distortion`

Transverse angular distortion for a fillet weld (Okerblom empirical).

`θ (rad) = 0.015 × HI_kJ_mm × leg_mm / t_mm²`

**Input:**
- `HI_kJ_mm` (required), `t_mm` (required), `leg_mm` (required)

**Returns:** `theta_rad`, `theta_deg`; flags > 3° and > 10°.

---

### `weld_longitudinal_distortion`

Longitudinal bowing distortion of a welded member.

`δ (mm) = 3.33 × HI_kJ_mm × L² / (A × E)`

**Input:**
- `HI_kJ_mm` (required), `length_mm` (required), `A_mm2` (required)
- `E_MPa` (default 210 000)

**Returns:** `delta_mm`; flags δ > L/1000.

---

### `weld_interpass_check`

Check interpass temperature compliance per AWS D1.1.

Requirements: T_interpass >= T_preheat AND T_interpass <= T_max (default 250 °C).

**Input:**
- `T_preheat_C` (required), `T_interpass_C` (required)
- `T_max_C` (default 250)

**Returns:** `compliant` (bool), `margin_below_max_C`, `warnings`.

---

## Example

```
1. weld_arc_heat_input  eta:0.85  V:26  I:200  v:4.0
   → HI_kJ_mm:1.105

2. weld_carbon_equivalent_iiw  C:0.18  Mn:1.4  Si:0.3  Cr:0.0  Mo:0.0  V:0.0
   → CE:0.413

3. weld_preheat_temperature  CE:0.413  t_mm:25  HI_kJ_mm:1.105
   → T_preheat_C:0  (no preheat required)

4. weld_fillet_volume  leg_mm:8  length_mm:200
   → volume_mm3:6400  throat_mm:5.66

5. weld_deposition_time  volume_mm3:6400  deposition_rate_kg_h:3.0
   → time_s:96  mass_kg:0.050
```
