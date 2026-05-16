# Earthworks & Site Grading

Pure-Python site earthworks and grading module covering cross-section areas,
volume calculation, borrow-pit grids, cut/fill balance, mass haul, Proctor
compaction, relative compaction, roller productivity, slope geometry, trench
excavation, and dewatering. References Peurifoy et al. (8th ed.), ASTM D698/D1557,
and USBR Design of Small Canal Structures.

---

## When to use

Reach for this module when the user asks about:

- cross-section area for a road or canal cut or fill (level, two-level, three-level)
- earthwork volume between stations using average-end-area or prismoidal method
- borrow-pit volume from a spot-elevation grid
- cut/fill balance with shrinkage and swell factors (bank/loose/compacted volumes)
- mass-haul diagram, balance points, overhaul cost, borrow/waste
- Proctor compaction curve: maximum dry density (MDD) and optimum moisture content (OMC)
- relative compaction (RC%) check against specification
- compaction roller productivity (area and volume per hour)
- slope daylight offset (cut or fill batter to ground)
- trench excavation volume with bedding and shoring quantities
- dewatering pump rate (Dupuit-Thiem formula for unconfined aquifer)
- road/canal grading, site preparation, earthmoving, or compaction QA

---

## Tools

### `earthworks_cross_section`

Compute cross-section area for a road/canal cut or fill.
Four methods: `level` (prismatic), `two-level` (asymmetric batters),
`three-level` (measured left/centre/right heights), `by-coords` (shoelace
formula from polygon coordinates).
Inputs vary by method — for `level`: `formation_width`, `centre_height`,
`side_slope`; for `by-coords`: `xs`, `ys` arrays.
Returns: `area_m2` and relevant geometry. Method defaults to `level`.

### `earthworks_volume`

Compute earthwork volume between cross-section stations.
Methods: `average-end-area` (default) or `prismoidal` (average-end-area minus
prismoidal correction).
Inputs: `stations` (list of chainages, m), `areas` (list of cross-section areas,
m²) — both required; optional `method`, `prismoidal_corrections`.
Returns: per-interval breakdown, `total_volume_m3`.

### `earthworks_borrow_pit`

Compute borrow-pit / spot-elevation grid volume by the four-quadrant grid method.
Node weights: corner=1, edge=2, interior=4. Positive = cut; negative = fill.
Inputs: `grid_spacing_x`, `grid_spacing_y`, `existing_elevations` (2-D array),
`design_elevation` — all required.
Returns: `total_volume_m3`, `cut_volume_m3`, `fill_volume_m3`.

### `earthworks_cut_fill_balance`

Balance cut and fill volumes accounting for material shrinkage and swell.
Volume states: Bank (BCM) → Loose (LCM) → Compacted (CCM).
Inputs: `cut_volume_bank_m3`, `fill_volume_compacted_m3` (required); optional
`shrinkage_factor` (compacted/bank, default 1.0), `swell_factor` (loose/bank),
`load_factor`.
Returns: surplus/deficit in bank measure, `borrow_required_m3`,
`waste_m3`, flags.

### `earthworks_mass_haul`

Compute mass-haul diagram: cumulative cut-minus-fill ordinates, balance points,
free-haul vs overhaul, and total cost.
Inputs: `stations`, `cut_volumes`, `fill_volumes` (all required); optional
`free_haul_distance` (default 500 m), `overhaul_cost_per_m3_station`,
`borrow_cost_per_m3`, `waste_cost_per_m3`.
Returns: `ordinates`, `balance_points`, total cut/fill, borrow/waste volumes,
cost breakdown.

### `earthworks_proctor`

Interpolate Proctor compaction curve (ASTM D698/D1557) to find MDD and OMC
by fitting a parabola through ≥ 3 (moisture_content, dry_density) data points.
Inputs: `moisture_contents` (list, %), `dry_densities` (list, kg/m³) — both
required.
Returns: `mdd_kg_m3`, `omc_pct`, polynomial coefficients, `r_squared`.

### `earthworks_relative_compaction`

Check field relative compaction against laboratory MDD and specification.
RC% = 100 × field_dry_density / lab_mdd.
Inputs: `field_dry_density`, `lab_mdd` (required); optional
`spec_rc_percent` (default 95).
Returns: `rc_percent`, `pass`, `deficit_percent`.

### `earthworks_lift_productivity`

Estimate compaction-roller productivity for a given lift.
Area productivity (m²/h) = roller_width × speed × efficiency / num_passes.
Inputs: `roller_width_m`, `roller_speed_kmh`, `lift_thickness_m`, `num_passes`
(all required); optional `efficiency_factor` (default 0.75).
Returns: `area_per_hour_m2`, `volume_per_hour_m3`.

### `earthworks_slope_daylight`

Compute horizontal offset from the formation edge to the daylight (hinge) point
for a cut or fill slope. Modes: `cut` (default) or `fill`.
Inputs: `formation_half_width`, `design_height_at_edge`,
`ground_height_at_edge`, `batter` (all required); optional `mode`.
Returns: `horizontal_offset_m`, `total_offset_from_cl_m`.

### `earthworks_trench`

Compute trench excavation volume with trapezoidal cross-section, bedding volume,
shoring area, and pipe volume deduction.
Inputs: `length_m`, `depth_m`, `bottom_width_m` (required); optional
`side_slope` (default 0 = vertical), `bedding_thickness_m`, `pipe_od_m`,
`shoring_area_per_m`.
Returns: `gross_volume_m3`, `net_volume_m3`, `bedding_volume_m3`,
`shoring_area_m2`, `top_width_m`.

### `earthworks_dewatering`

Estimate steady-state pump rate for well-point dewatering in an unconfined
aquifer using the Dupuit-Thiem formula: Q = π·K·(H² − hw²) / ln(R/r).
Inputs: `hydraulic_conductivity_m_s`, `aquifer_thickness_m`, `drawdown_m`,
`radius_of_influence_m`, `equivalent_well_radius_m` (all required).
Returns: `pump_rate_m3_s`, `pump_rate_m3_h`, `pump_rate_L_s`.

---

## Example

**User ask:** "Road cut: 7 m formation, 1.5:1 batters, centre height 2.4 m.
Stations at 0, 25, and 50 m with areas to be computed. What is the total volume
by average-end-area?"

1. `earthworks_cross_section` — method: level, formation_width: 7,
   centre_height: 2.4, side_slope: 1.5  → area_m2 (repeat for each station)
2. `earthworks_volume` — stations: [0, 25, 50], areas: [A0, A25, A50]
   → total_volume_m3

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Tools are **stateless** — validate and return dicts; no DB writes.
- Invalid inputs return `{ok: false, reason: "..."}` — never raise.
