# Manufacturing Should-Cost Estimation

Pure-Python manufacturing cost estimation (should-cost) tools. No OCC dependency.
All tools are stateless. Currency units are generic (consistent across a session).

---

## When to use

Use these tools when the conversation involves: should-cost, unit cost, CNC
machining cost, casting cost, injection moulding cost, sheet metal fabrication
cost, 3D printing cost, additive manufacturing cost, assembly labour cost, cost
roll-up, overhead, SG&A, gross margin, selling price, batch size, setup cost,
tooling amortisation, learning curve, Wright curve, experience curve, make vs buy,
break-even volume, batch curve, variable cost, fixed cost, manufacturing economics.

---

## Tools

### `costing_cnc`

CNC machining parametric should-cost per unit.

**Input:** `material_cost`, `cycle_time_hr`, `machine_rate_per_hr` (required);
optional `setup_time_hr` (default 0.5), `batch_size` (default 1),
`tooling_cost` (default 0), `tooling_life_parts` (default 1000),
`overhead_rate` (default 0.15).

**Returns:** unit cost breakdown (material, machine, setup, tooling, overhead,
total), warnings (setup-dominated for small batches).

---

### `costing_casting`

Sand / investment casting parametric should-cost per unit.

**Input:** `material_cost_per_kg`, `part_mass_kg` (required); optional
`yield_fraction` (default 0.70), `pattern_cost`, `pattern_life_parts`,
`finishing_cost_per_part`, `machine_rate_per_hr`, `pour_time_hr`,
`batch_size`, `overhead_rate`.

**Returns:** unit cost breakdown, warnings.

---

### `costing_injection`

Injection moulding parametric should-cost per good part.

**Input:** `material_cost_per_kg`, `shot_mass_kg` (required); optional
`scrap_rate` (default 0.03), `cycle_time_hr`, `machine_rate_per_hr`,
`mould_cost`, `mould_life_shots`, `cavities`, `batch_size`, `overhead_rate`.

**Returns:** unit cost breakdown, warnings (small batch, high scrap).

---

### `costing_sheet_metal`

Sheet-metal fabrication should-cost per part.

**Input:** `blank_area_m2`, `material_cost_per_kg`, `material_density_kg_m3`,
`sheet_thickness_m` (all required); optional `num_bends`, `bend_time_hr`,
`press_rate_per_hr`, `laser_cut_rate_per_hr`, `cut_perimeter_m`,
`cut_speed_m_per_hr`, `setup_cost`, `batch_size`, `overhead_rate`.

**Returns:** unit cost breakdown by category.

---

### `costing_printing`

3D printing (FDM/SLA/SLS) should-cost per part.

**Input:** `material_volume_cm3`, `material_cost_per_cm3`, `build_time_hr`,
`machine_rate_per_hr` (all required); optional `support_volume_fraction`
(default 0.15), `post_processing_cost`, `batch_size`, `machine_utilisation`
(default 0.80), `overhead_rate`.

**Returns:** unit cost breakdown.

---

### `costing_assembly`

Labour-time-based assembly should-cost.

**Input:** `operations` (required) — list of `{name, time_hr, rate_per_hr}`;
optional `overhead_rate` (default 0.20).

**Returns:** `total_labour`, `total_overhead`, `total_cost`, per-operation
breakdown.

---

### `costing_rollup`

Generic manufacturing cost roll-up to unit selling price.

Waterfall: direct costs → +overhead% → manufacturing cost → +SG&A% →
full cost → ÷(1−margin%) → unit price.

**Input:** `direct_material`, `direct_labour`, `machine_cost` (all required);
optional `setup_cost_per_batch`, `batch_size`, `tooling_amortisation`,
`overhead_rate` (default 0.20), `sga_rate` (default 0.10),
`margin_rate` (default 0.20).

**Returns:** full waterfall breakdown, warnings (negative margin, setup-dominated).

---

### `costing_batch_curve`

Unit cost vs. batch-size breakpoints.

unit_cost(n) = variable_cost_per_unit + fixed_cost_per_run / n

**Input:** `fixed_cost_per_run`, `variable_cost_per_unit`, `batch_sizes`
(list of integers).

**Returns:** list of `{batch_size, unit_cost}`, `min_unit_cost`, `max_unit_cost`.

---

### `costing_learning_curve`

Wright (1936) learning curve — unit cost at cumulative production volume.

T_n = T_1 × n^b, where b = log(learning_rate) / log(2).

**Input:** `t1` (unit cost at volume = 1), `cumulative_volume`; optional
`learning_rate` (default 0.80 = 80%).

**Returns:** `unit_cost_at_n`, `learning_exponent_b`.

---

### `costing_make_vs_buy`

Make vs. buy comparison with break-even volume.

**Input:** `make_unit_cost`, `buy_unit_price` (required); optional
`make_fixed_cost`, `annual_volume`, `make_lead_time_days`,
`buy_lead_time_days`.

**Returns:** `annual_make_cost`, `annual_buy_cost`, `break_even_volume`,
`preferred` (`"make"` or `"buy"`), comparison table.

---

## Example

```
1. costing_cnc  material_cost:12  cycle_time_hr:0.25  machine_rate_per_hr:75
                setup_time_hr:1.0  batch_size:50  tooling_cost:500
   → unit_cost: 32.85  (material:12, machine:18.75, setup:1.50, tooling:0.50, overhead:0.10)

2. costing_rollup  direct_material:12  direct_labour:5  machine_cost:18.75
                   overhead_rate:0.20  sga_rate:0.10  margin_rate:0.25
   → unit_price: 54.38

3. costing_make_vs_buy  make_unit_cost:32.85  buy_unit_price:28.00
                        make_fixed_cost:5000  annual_volume:200
   → preferred:"buy"  break_even_volume:1000
```
