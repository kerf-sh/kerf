# Stormwater Hydrology

Pure-Python stormwater hydrology tools: peak flow estimation, runoff depth, time of
concentration, IDF intensity, detention basin sizing, routing, and storm sewer pipe
sizing. No OCC dependency. Units: SI (m³/s, mm, ha, km², hr). References: ASCE/EWRI 45-05;
TR-55 (USDA SCS 1986); NRCS NEH-630; Chow, Maidment & Mays (1988).

---

## When to use

Use these tools when the user asks about:
- stormwater, hydrology, runoff, peak flow
- Rational method, Q = C·i·A, catchment flow
- runoff coefficient, composite C
- SCS curve number, CN, runoff depth, NRCS, TR-55
- time of concentration, Tc, Kirpich, NRCS velocity method, sheet flow
- IDF curve, intensity-duration-frequency, rainfall intensity
- detention basin, retention pond, detention storage, modified rational method
- level-pool routing, Puls routing, storage-indication method, hydrograph routing
- storm sewer, pipe sizing, Manning equation, pipe diameter selection, self-cleansing velocity

---

## Tools

### `hydrology_rational_peak_flow`

Rational-method peak stormwater flow.

`Q = C · i · A / 360`  (Q in m³/s, i in mm/hr, A in ha)

**Input:**
- `C` (required) — runoff coefficient (0 < C ≤ 1; typical 0.90 impervious, 0.35 lawn)
- `i_mm_hr` (required) — design rainfall intensity (mm/hr)
- `A_ha` (required) — catchment area (ha)

**Returns:** `Q_m3s`, `Q_L_per_s`.

---

### `hydrology_composite_runoff_coeff`

Area-weighted composite runoff coefficient for mixed land-cover catchments.

`C_composite = Σ(Ci × Ai) / Σ(Ai)`

**Input:**
- `areas` (required) — list of `{C: number, area_ha: number}` objects

**Returns:** `C_composite`, `total_area_ha`.

---

### `hydrology_scs_runoff_depth`

SCS/NRCS curve-number runoff depth (NEH-630, TR-55).

```
S = 25400/CN − 254  (mm)
Ia = 0.2 × S
Q = (P − Ia)² / (P − Ia + S)   for P > Ia
```

**Input:**
- `P_mm` (required) — total storm rainfall (mm)
- `CN` (required) — SCS runoff curve number (1–100)

**Returns:** `Q_mm` (runoff depth), `S_mm`, `Ia_mm`.

---

### `hydrology_scs_peak_flow`

SCS/TR-55 graphical-peak flow for a small watershed (TR-55 Chapter 4).

Interpolates unit peak discharge `qu` from TR-55 Appendix B tables;
`Qp = qu × A × Q`.

**Input:**
- `CN` (required), `A_km2` (required), `tc_hr` (required, valid 0.1–2.0 hr),
  `P_mm` (required) — 24-hour design rainfall

**Returns:** `Qp_m3s`, `Q_mm`, `qu`, `Ia_P_ratio`.

---

### `hydrology_time_of_concentration`

Time of concentration using one of three methods.

**Input:**
- `method` (required) — `kirpich`, `nrcs_velocity`, or `sheet_shallow_channel`
- `kirpich`: `L_m` (channel length), `H_m` (elevation drop)
- `nrcs_velocity`: `L_m`, `slope` (m/m), `cover` (land cover type string)
- `sheet_shallow_channel`: `sheet_length_m`, `sheet_n`, `sheet_P2_mm`, `sheet_slope`,
  `shallow_length_m`, `shallow_slope`, `shallow_cover`,
  `channel_length_m`, `channel_slope`, `channel_area_m2`,
  `channel_wetted_perim_m`, `channel_n`

**Returns:** `tc_hr`, `tc_min`, `method`, `warnings`, sub-times per segment.

---

### `hydrology_idf_intensity`

Design rainfall intensity from a fitted IDF formula.

`i = a / (t + b)^c`  (mm/hr, t in minutes)

**Input:**
- `duration_min` (required), `a` (required), `b` (required), `c` (required)

**Returns:** `intensity_mm_hr`.

---

### `hydrology_detention_storage`

Required detention basin storage volume (modified-rational method).

`V ≈ 0.5 × (Q_in − Q_out) × tc × 3600`  (m³)

**Input:**
- `Q_in_cms` (required) — design-storm peak inflow (m³/s)
- `Q_out_cms` (required) — allowable release rate (m³/s)
- `tc_hr` (required) — time of concentration (hr)

**Returns:** `V_m3`.

---

### `hydrology_storage_indication_route`

Route an inflow hydrograph through a detention basin using the storage-indication
(Puls / level-pool) method.

```
(S/Δt + O/2)|₂ = (I₁ + I₂)/2 + (S/Δt − O/2)|₁
```

Outflow from user-supplied stage-storage-outflow rating table via linear interpolation.

**Input:**
- `inflow_series` (required) — inflow hydrograph ordinates (m³/s) at uniform time step
- `outflow_rating` (required) — list of `{storage_m3, outflow_m3s}` objects, sorted ascending
- `dt_s` (required) — time step (s)
- `S0_m3` — initial storage (m³, default 0)

**Returns:** `outflow_m3s` list, `storage_m3` list, `peak_outflow_m3s`, `peak_storage_m3`.

---

### `hydrology_storm_sewer_pipe_size`

Select minimum standard circular storm-sewer diameter using Manning full-flow equation.

`Q = (1/n) · (π/4)·D² · (D/4)^(2/3) · S^(1/2)`

Selects smallest ASTM/ISO nominal diameter where Q_full ≥ Q_design / freeboard_fraction.

**Input:**
- `Q_cms` (required) — design peak flow (m³/s)
- `slope` (required) — hydraulic gradient (m/m)
- `n` — Manning roughness (default 0.013 concrete; 0.010 PVC, 0.011 HDPE)
- `min_d_m` — minimum diameter (default 0.15 m)
- `max_d_m` — maximum diameter (default 3.0 m)
- `freeboard_fraction` — design/full-flow capacity ratio (default 0.85)

**Returns:** `diameter_m`, `diameter_mm`, `Q_full_m3s`, `utilisation`, `freeboard_ok`.

---

## Example

```
1. hydrology_idf_intensity  duration_min:30  a:1200  b:10  c:0.8
   → intensity_mm_hr:58.3

2. hydrology_rational_peak_flow  C:0.75  i_mm_hr:58.3  A_ha:5.0
   → Q_m3s:0.0607  Q_L_per_s:60.7

3. hydrology_time_of_concentration  method:"kirpich"  L_m:800  H_m:20
   → tc_hr:0.28  tc_min:16.7

4. hydrology_storm_sewer_pipe_size  Q_cms:0.061  slope:0.003
   → diameter_mm:450  utilisation:0.72  freeboard_ok:true
```
