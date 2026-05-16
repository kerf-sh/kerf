# Rolling Bearing Selection & Life — LLM Reference

ISO 281 / ISO 76 rolling-bearing calculations. No OCC dependency. All tools are
stateless — they compute and return results; no DB write. Units: N, mm, rpm, hours.

---

## When to use

Keywords: bearing, rolling bearing, ball bearing, roller bearing, bearing life, L10,
Lna, rating life, dynamic load rating, static load rating, equivalent load, bearing
selection, SKF, bearing catalogue, grease interval, relubrication, speed limit,
Sommerfeld, ISO 281, fatigue life, bearing hours.

---

## Workflow

```
bearing_equivalent_load → bearing_rating_life → bearing_adjusted_life
bearing_required_capacity → bearing_select (catalogue lookup)
bearing_static_safety  (static shock check)
bearing_limiting_speed (overspeed check)
bearing_grease_interval (maintenance schedule)
```

---

## Tools

### `bearing_equivalent_load`

Compute equivalent dynamic bearing load P = X·Fr + Y·Fa per ISO 281 Table 4.

**Input:** `Fr` (radial force, N), `Fa` (axial force, N), `bearing_type` (`"ball"` default / `"angular-contact"` / `"roller"`), `C0` (static rating, N — improves Y interpolation for ball bearings).

**Returns:** `P_N`, `X`, `Y`, `e` ratio, warnings.

---

### `bearing_rating_life`

ISO 281 basic rating life L10 = (C/P)^p [10⁶ rev].

**Input:** `C` (dynamic load rating, N), `P` (equivalent load, N), `bearing_type` (`"ball"` p=3 / `"roller"` p=10/3), `n_rpm` (optional — adds L10_hours).

**Returns:** `L10_rev`, optionally `L10_hours`, `C_over_P`; warns if C/P < 1.

---

### `bearing_adjusted_life`

Adjusted (modified) ISO 281 rating life Lna = a1 × a23 × L10.

**Input:** `C` (N), `P` (N), `n_rpm` (rpm), `bearing_type`, `a1` (reliability factor: 1.0 = 90%, 0.62 = 95%, 0.44 = 97%, 0.21 = 99%), `a23` (lubrication/contamination factor, default 1.0).

**Returns:** `L10_rev`, `Lna_rev`, `L10_hours`, `Lna_hours`, warnings.

---

### `bearing_static_safety`

Static safety factor s0 = C0 / P0 per ISO 76.

**Input:** `C0` (static load rating, N), `P0` (equivalent static load, N).

**Returns:** `s0`; warns for s0 < 1.0. Recommended minimums: 0.8 (smooth), 1.0 (normal), 1.5 (moderate shock), 2.0 (heavy shock).

---

### `bearing_required_capacity`

Required dynamic load rating C to achieve a target adjusted life.

**Input:** `P` (N), `n_rpm`, `Lh_target` (hours), `bearing_type`, `a1`, `a23`.

**Returns:** `C_required_N` — minimum catalogue C to select.

---

### `bearing_limiting_speed`

Check n·dm speed parameter against SKF grease-lubrication limits.

**Input:** `dm_mm` (pitch diameter = (bore + OD)/2, mm), `n_rpm`, `bearing_type` (`"ball"` limit 600 000 mm·rpm / `"roller"` limit 300 000 mm·rpm).

**Returns:** `ndm`, `ndm_limit`, `utilisation` fraction; warns if over limit.

---

### `bearing_grease_interval`

Estimate grease relubrication interval in hours (SKF handbook method).

**Input:** `dm_mm`, `n_rpm`, `C_kN` (dynamic load rating, kN), `P_kN` (equivalent load, kN).

**Returns:** `relubrication_hours`; warns if n·√dm ≥ 14×10⁶ (use oil lubrication).

---

### `bearing_select`

Select lightest bearing from a built-in series table meeting life and static safety targets.

**Input:** `series` (`"6000"` / `"6200"` / `"6300"` / `"NU200"`), `Fr` (N), `Fa` (N), `n_rpm`, `Lh_min` (hours), `bearing_type`, `a1`, `a23`, `s0_min`.

**Returns:** selected bearing dict (bore, OD, C, C0, mass) or `null`; list of all candidates with their computed adjusted lives.

---

## Example

```
# Select a 6200-series ball bearing for Fr=2500 N, Fa=500 N,
# 1500 rpm, 10 000 h target life at 90% reliability.

bearing_equivalent_load  Fr:2500  Fa:500  bearing_type:"ball"
  → P_N: 2670  X: 0.56  Y: 1.45  e: 0.44

bearing_required_capacity  P:2670  n_rpm:1500  Lh_target:10000
  → C_required_N: 29 400

bearing_select  series:"6200"  Fr:2500  Fa:500  n_rpm:1500  Lh_min:10000
  → selected: {designation:"6210", bore_mm:50, OD_mm:90, C_N:35100, ...}
```
