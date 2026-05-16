# Thermal & Abrasive Cutting Processes

Pure-Python thermal and abrasive cutting process engineering. No OCC dependency. All tools are
stateless. Processes: laser, plasma, oxyfuel, waterjet (AWJ). References: Steen & Mazumder (2010),
ESAB Plasma Handbook, Hashish (1989).

---

## When to use

Laser cutting, plasma cutting, oxyfuel cutting, oxy-acetylene, oxy-propane, waterjet, abrasive
waterjet, AWJ, cut speed, traverse speed, kerf width, heat-affected zone, HAZ, pierce time,
edge quality, dross, assist gas, gas consumption, part cost, process selection, sheet metal cutting,
mild steel cutting, stainless cutting, aluminium cutting, cutting comparison.

---

## Tools

### `thermalcut_laser_speed`

Maximum laser cut speed (mm/min) from power and thickness. Energy-balance model:
v = η·P / (ρ·H·t·w_k).

**Input:** `thickness_mm` (required), `power_W` (required), `material` (default `'mild_steel'`),
`assist_gas` (`'O2'`/`'N2'`/`'Air'`, default `'O2'`), `efficiency`, `kerf_mm`

**Returns:** `speed_mm_min`, `kerf_mm`, `heat_content_J_kg`, warnings

---

### `thermalcut_plasma_speed`

Maximum plasma cut speed (mm/min). Arc power = voltage × amperage.

**Input:** `thickness_mm` (required), `amperage` (A, required), `material`, `voltage` (default 130 V),
`efficiency` (default 0.48)

**Returns:** `speed_mm_min`, `arc_power_W`, `kerf_mm`, warnings

---

### `thermalcut_oxyfuel_speed`

Empirical oxyfuel traverse speed (mm/min) from published Lincoln Electric data.
Valid for `mild_steel` and `tool_steel` only.

**Input:** `thickness_mm` (required, range 1–300 mm), `material`

**Returns:** `speed_mm_min`

---

### `thermalcut_waterjet_speed`

AWJ traverse speed (mm/min) using the Hashish (1989) machinability model.
v = C_m · P_j^1.25 · m_a^0.687 / (t · d_f^1.15 · N_m).

**Input:** `thickness_mm` (required), `material`, `pump_power_kW` (default 30),
`orifice_dia_mm` (default 0.356), `abrasive_rate_kg_min` (default 0.45),
`machinability_number` (optional override)

**Returns:** `speed_mm_min`, `jet_power_W`, `mixing_tube_dia_mm`, warnings

---

### `thermalcut_kerf_width`

Empirical kerf width (mm) for a given process and thickness.

**Input:** `process` (`'laser'`/`'plasma'`/`'oxyfuel'`/`'waterjet'`, required),
`thickness_mm` (required), `power_or_amp` (required)

**Returns:** `kerf_mm`

---

### `thermalcut_haz_width`

Heat-affected zone (HAZ) width (mm) at cut edge. Waterjet returns 0 (cold process).
Model: HAZ = k_mat · √(P / (v·t)).

**Input:** `process` (required), `thickness_mm` (required), `speed_mm_min` (required),
`power_or_amp` (required), `material`

**Returns:** `haz_mm`

---

### `thermalcut_pierce_time`

Pierce/punch-through time (seconds) before traverse begins.

**Input:** `process` (required), `thickness_mm` (required), `power_W` (laser),
`amperage` (plasma)

**Returns:** `pierce_time_s`

---

### `thermalcut_edge_quality`

Edge quality regime and dross risk from actual vs nominal speed ratio.
Regimes: `too_slow`, `slow`, `optimal`, `fast`, `too_fast`.

**Input:** `process` (required), `speed_mm_min` (required), `nominal_speed_mm_min` (required)

**Returns:** `regime`, `dross_risk`, `quality`

---

### `thermalcut_gas_consumption`

Assist/fuel gas consumption (litres) and cost (USD) for a cut.

**Input:** `process` (required), `thickness_mm` (required), `cut_length_mm` (required),
`speed_mm_min` (required), `assist_gas` (laser default `'O2'`)

**Returns:** `gas_volume_L`, `cost_usd`, gas type breakdown

---

### `thermalcut_waterjet_params`

AWJ orifice/mixing-tube sizing, jet power, standoff distance, and abrasive loading ratio.
Orifice flow: Q = C_d·A·√(2·ΔP/ρ).

**Input:** `pump_power_kW` (required), `orifice_dia_mm` (required),
`mixing_tube_dia_mm`, `mixing_tube_length_mm`, `pressure_MPa` (default 380),
`abrasive_rate_kg_min` (default 0.45)

**Returns:** `jet_power_W`, `Q_water_m3s`, `mixing_tube_dia_mm`, `abrasive_loading_ratio`

---

### `thermalcut_part_cost`

Total part cutting cost (USD).
Cost = (cut_time + pierce_time) × machine_rate + consumables.

**Input:** `process` (required), `cut_length_mm` (required), `speed_mm_min` (required),
`n_pierces` (required), `pierce_time_s` (required), `machine_rate_usd_hr` (optional),
`consumables_cost_usd`

**Returns:** `cost_usd`, `cut_time_min`, `pierce_time_total_s`

---

### `thermalcut_process_compare`

Side-by-side comparison of all four processes for a material/thickness, returning speed, kerf, HAZ,
pierce time, and part cost for each.

**Input:** `thickness_mm` (required), `material` (default `'mild_steel'`),
`cut_length_mm` (default 1000), `n_pierces` (default 4)

**Returns:** per-process `speed_mm_min`, `kerf_mm`, `haz_mm`, `pierce_time_s`, `part_cost_usd`

---

## Example

```
1. thermalcut_process_compare  thickness_mm:10  material:"mild_steel"
   → laser: 2800 mm/min, kerf:0.24mm, HAZ:0.35mm, cost:$0.38
   → plasma: 3200 mm/min, kerf:1.8mm, HAZ:0.9mm, cost:$0.24
   → waterjet: 180 mm/min, kerf:1.3mm, HAZ:0mm, cost:$0.81

2. thermalcut_laser_speed  thickness_mm:10  power_W:4000  material:"stainless_304"
   → speed_mm_min: 1850  kerf_mm: 0.22
```
