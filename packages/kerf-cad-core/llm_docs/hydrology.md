# Stormwater Hydrology

Pure-Python stormwater hydrology tools: peak flow estimation, runoff depth, time of
concentration, IDF intensity, detention basin sizing, routing, and storm sewer pipe
sizing. No OCC dependency. Units: SI (m³/s, mm, ha, km², hr).

Authoritative standards:
- **NRCS TR-55 (USDA SCS 1986)** — *Urban Hydrology for Small Watersheds*,
  Technical Release 55 — SCS curve-number runoff, graphical-peak-flow method.
- **NRCS NEH-630 (2004)** — *National Engineering Handbook, Part 630 Hydrology* —
  curve-number theory, Ia = 0.2·S.
- **Rational Method (Mulvaney 1851; Kuichling 1889)** — Q = C·i·A; ASCE/EWRI
  Manual of Engineering Practice No. 36 (2005).
- **ASCE/EWRI 45-05** — *Standard Guidelines for the Design of Urban Stormwater
  Systems* — pipe-sizing criteria, Manning roughness, self-cleansing velocity.
- **Kirpich (1940)** — "Time of concentration of small agricultural watersheds,"
  *Civil Engineering*, 10(6):362 — Tc formula.
- **Chow, Maidment & Mays (1988)** — *Applied Hydrology* — storage-indication
  routing, general hydrology.
- **Puls (1928) / Level-pool routing** — conservation of mass for detention basins.

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
- storm sewer, pipe sizing, Manning equation, pipe diameter selection, self-cleansing
  velocity

---

## Tools

### `hydrology_rational_peak_flow`

Rational-method peak stormwater flow.

```
Q = C · i · A / 360        (Q m³/s, i mm/hr, A ha)
```

**Input:** `C` (required, 0 < C ≤ 1), `i_mm_hr`, `A_ha`.

**Returns:** `Q_m3s`, `Q_L_per_s`.

**Standards alignment:** ASCE/EWRI Manual 36 (2005) §3.2; original Kuichling
(1889) formulation. Valid for catchments < 80 ha (200 ac) with uniform runoff
conditions. C values: impervious 0.90–0.95; lawn/turf 0.25–0.35; commercial
0.70–0.95 per ASCE Table 3-1.

---

### `hydrology_composite_runoff_coeff`

Area-weighted composite runoff coefficient for mixed land-cover catchments.

```
C_composite = Σ(Ci × Ai) / Σ(Ai)
```

**Standards alignment:** ASCE/EWRI Manual 36 §3.2.1; ASCE Standard Practice
for the Design of Stormwater Management Systems.

---

### `hydrology_scs_runoff_depth`

SCS/NRCS curve-number runoff depth — **NEH-630, TR-55**.

```
S = 25400/CN − 254          (maximum potential retention, mm)
Ia = 0.2·S                  (initial abstraction)
Q = (P − Ia)² / (P − Ia + S)  for P > Ia   [TR-55 Eq. 2-1]
Q = 0                        for P ≤ Ia
```

**Input:** `P_mm` (total storm rainfall, mm), `CN` (1–100).

**Returns:** `Q_mm` (runoff depth), `S_mm`, `Ia_mm`.

**Standards alignment:** NRCS NEH-630 §10.2 (CN method); TR-55 Chapter 2 (Eq.
2-1); Ia = 0.2S is the standard (NEH-630 §10.4 notes Ia = 0.05S for better urban
fit — applies Ia=0.2S by default per TR-55 convention).

---

### `hydrology_scs_peak_flow`

SCS/TR-55 graphical-peak flow for a small watershed — **TR-55 Chapter 4**.

Uses unit-peak-discharge qu from TR-55 Appendix B tables interpolated by Tc and
Ia/P ratio:
```
Qp = qu × A_km2 × Q_mm / 1000    (m³/s)    [TR-55 Eq. 4-1]
```

**Input:** `CN`, `A_km2`, `tc_hr` (0.1–2.0 hr), `P_mm` (24-hr design rainfall).

**Returns:** `Qp_m3s`, `Q_mm`, `qu`, `Ia_P_ratio`.

**Standards alignment:** TR-55 Chapter 4 (graphical peak-flow method); Appendix
B tabular qu values for Type I, IA, II, III storm distributions. Implementation
uses Type II (eastern US, general) as default; override by selecting distribution
manually. Valid for A_km2 ≤ 25 km², single main channel, no ponding.

---

### `hydrology_time_of_concentration`

Time of concentration using one of three methods.

**Kirpich (1940):**
```
tc = 0.0663·(L^0.77 / H^0.385)    (hr, L = channel length m, H = elevation drop m)
```

**NRCS velocity method (NEH-630 §15.4):**
```
tc = L / (3600·V_avg)    where V_avg from land-cover velocity table
```

**Sheet–shallow–channel (TR-55 §3):**
```
t_sheet = 0.007·(nP2)^0.8 / (P2^0.5·S^0.4)   [TR-55 Eq. 3-3, hr]
t_shallow = L / (3600·V_shallow)
t_channel = L / (3600·V_channel)
tc = t_sheet + t_shallow + t_channel
```

**Input:** `method` (`kirpich`, `nrcs_velocity`, or `sheet_shallow_channel`)
plus method-specific parameters.

**Returns:** `tc_hr`, `tc_min`, `method`, `warnings`, sub-times per segment.

**Standards alignment:**
- Kirpich: Kirpich (1940) — calibrated on Tennessee farm watersheds; ASCE
  Manual 36 §3.4 (use with caution outside calibration range).
- NRCS velocity: NEH-630 §15.4; velocity table from TR-55 Exhibit 3-1.
- Sheet/shallow/channel: TR-55 §3; recommended maximum sheet-flow length 91 m
  (300 ft) per TR-55 §3.2; Mannings n for sheet flow from TR-55 Table 3-1.

---

### `hydrology_idf_intensity`

Design rainfall intensity from a fitted IDF formula.

```
i = a / (t + b)^c          (mm/hr, t in minutes)
```

**Input:** `duration_min`, `a`, `b`, `c` (IDF parameters from regional curves).

**Returns:** `intensity_mm_hr`.

**Standards alignment:** Three-parameter power-law IDF form per Chow et al.
(1988) §3.2; regional a/b/c from NOAA Atlas 14 (US), equivalent national rain
charts, or local drainage manuals.

---

### `hydrology_detention_storage`

Required detention basin storage volume — modified-rational method.

```
V ≈ 0.5·(Q_in − Q_out)·tc·3600   (m³)
```

**Standards alignment:** Modified-rational method (ASCE Manual 36 §4.2);
conservative upper bound on required storage for simple triangular inflow
hydrograph. For more accurate sizing, use `hydrology_storage_indication_route`.

---

### `hydrology_storage_indication_route`

Route an inflow hydrograph through a detention basin — storage-indication (Puls /
level-pool) method.

```
Conservation of mass (Puls 1928):
(S/Δt + O/2)|₂ = (I₁ + I₂)/2 + (S/Δt − O/2)|₁
```

Outflow from user-supplied stage-storage-outflow rating table via linear
interpolation.

**Input:** `inflow_series` (m³/s), `outflow_rating` (list of `{storage_m3,
outflow_m3s}`), `dt_s`, `S0_m3`.

**Returns:** `outflow_m3s`, `storage_m3`, `peak_outflow_m3s`, `peak_storage_m3`.

**Standards alignment:** Chow et al. (1988) §8.8 (storage-indication method);
Puls (1928) continuity approximation; USACE HEC-HMS computational basis for
simplified routing.

---

### `hydrology_storm_sewer_pipe_size`

Select minimum standard circular storm-sewer diameter — Manning full-flow.

```
Q_full = (1/n)·(π/4)·D²·(D/4)^(2/3)·S^(1/2)
Select smallest standard D where Q_full ≥ Q_design / freeboard_fraction
```

Standard diameters (mm): 150, 225, 300, 375, 450, 525, 600, 675, 750, 900,
1050, 1200, 1350, 1500, 1800, 2100, 2400, 3000.

**Input:** `Q_cms`, `slope`, `n` (default 0.013 concrete), `min_d_m`, `max_d_m`,
`freeboard_fraction` (default 0.85).

**Returns:** `diameter_m`, `diameter_mm`, `Q_full_m3s`, `utilisation`,
`freeboard_ok`.

**Standards alignment:** ASCE/EWRI 45-05 §5.4 (Manning full-flow pipe sizing);
ASTM/ISO standard pipe sizes; minimum velocity 0.9 m/s (3 ft/s) for self-
cleansing — check full-flow velocity (V_full = Q_full/A) against minimum.

---

## Example

```
1. hydrology_idf_intensity  duration_min:30  a:1200  b:10  c:0.8
   → intensity_mm_hr:58.3

2. hydrology_rational_peak_flow  C:0.75  i_mm_hr:58.3  A_ha:5.0
   → Q_m3s:0.0607  Q_L_per_s:60.7   [Q=C·i·A/360]

3. hydrology_scs_runoff_depth  P_mm:75  CN:80
   → S_mm:63.5  Ia_mm:12.7  Q_mm:30.4  [TR-55 Eq. 2-1]

4. hydrology_time_of_concentration  method:"kirpich"  L_m:800  H_m:20
   → tc_hr:0.28  tc_min:16.7  [Kirpich 1940]

5. hydrology_storm_sewer_pipe_size  Q_cms:0.061  slope:0.003
   → diameter_mm:450  utilisation:0.72  freeboard_ok:true
   [ASCE/EWRI 45-05; Manning n=0.013; Q_full=0.085 m³/s]
```
