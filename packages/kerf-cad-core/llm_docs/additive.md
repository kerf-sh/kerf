# Additive Manufacturing — DFAM and Process Planning

Pure-Python additive manufacturing (AM) design-for-AM (DFAM) and process
planning tools. No OCC dependency. All tools are stateless. Supported processes:
FDM, SLA, SLS, MJF, DMLS.

---

## When to use

Use these tools when the conversation involves: 3D printing, additive
manufacturing, FDM, FFF, SLA, stereolithography, SLS, selective laser sintering,
MJF, Multi Jet Fusion, DMLS, direct metal laser sintering, DFAM, build time,
support structure, overhang, overhang angle, support removal, build orientation,
orientation optimisation, shrinkage, warping, lattice infill, gyroid, cubic,
Gibson-Ashby, effective modulus, porous, minimum wall thickness, minimum hole,
bridging span, feature checks, printability, nesting, powder bed, packing
efficiency, part cost, machine rate, FDM material, SLS material, DMLS material,
PLA, ABS, nylon, PA12, resin, 316L, AlSi10Mg, Ti6Al4V.

---

## Tools

### `am_process_params`

Return the built-in process parameter record for an AM process.

**Input:** `process` (`FDM`|`SLA`|`SLS`|`MJF`|`DMLS`).

**Returns:** `overhang_threshold_deg`, `min_wall_m`, `min_hole_m`,
`max_bridge_m`, `default_layer_thickness_m`, `layer_time_coeff`,
`default_machine_rate_per_h`, `uses_supports`, `is_powder_bed`.

---

### `am_build_time_estimate`

Estimate AM build time from bounding box and process parameters.

Model: layer_count = ceil(z / layer_thickness); time per layer proportional
to cross-section area × fill fraction.

**Input:** `process`, `bounding_box_m` ([x, y, z], z = build height); optional
`layer_thickness_m`, `fill_fraction` (default 0.20), `travel_overhead_frac`
(default 0.15), `cross_section_m2`.

**Returns:** `layer_count`, `build_time_s`, `build_time_h`.

---

### `am_support_volume`

Estimate support-structure volume from overhang projection.

**Input:** `part_volume_m3`, `projected_area_m2` (required); optional
`overhang_fraction` (default 0.20), `support_density` (default 0.15),
`support_height_m`, `bounding_z_m`.

**Returns:** `support_volume_m3`, `support_to_part_ratio`.

---

### `am_overhang_removability`

Assess overhang printability and support-removal difficulty.

Angle convention: 0° = vertical wall; 90° = horizontal ceiling.

**Input:** `process`, `overhang_angle_deg`.

**Returns:** `needs_support`, `removability` (`easy`/`moderate`/`difficult`/`N/A`),
`risk_description`. SLS and MJF are always self-supporting.

---

### `am_orientation_cost`

Scalar orientation cost for one candidate build orientation.

Cost = w_support × (overhang/surface) + w_height × (z/max_bbox)
      + w_surface × (surface/sphere_equiv). Lower = better.

**Input:** `process`, `part_bbox_m` ([x, y, z]), `surface_area_m2`,
`overhang_area_m2`; optional weights `w_support` (default 1.0),
`w_height` (default 0.5), `w_surface` (default 0.3).

**Returns:** `cost`, `support_term`, `height_term`, `surface_term`.

---

### `am_best_orientation`

Select best build orientation from N candidates by minimum cost.

**Input:** `process`, `part_bbox_m_list` (list of [x,y,z]),
`surface_area_m2`, `overhang_areas_m2` (list); optional weights.

**Returns:** `best_index` (0-based), `best_cost`, `all_costs`.

---

### `am_shrinkage_compensation`

Scale-up dimension to compensate for AM process shrinkage.

compensated_dim = nominal_dim / (1 − shrinkage_fraction).

**Input:** `nominal_dim_m`, `process`; optional `material` (process-specific).

**Returns:** `shrinkage_fraction`, `compensated_dim_m`, `scale_factor`.
SLS/MJF PA12 has the largest shrinkage (~2.8–3.0%).

---

### `am_lattice_infill`

Gibson-Ashby lattice effective properties for an AM part.

- `gyroid` (bending-dominated): E_eff = 0.3 × ρ_rel² × E_solid
- `cubic` (stretch-dominated): E_eff = 1.0 × ρ_rel × E_solid

**Input:** `process`, `infill_type` (`gyroid`|`cubic`), `relative_density`
(0–1), `solid_modulus_Pa`, `solid_density_kg_m3`, `volume_m3`.

**Returns:** `effective_modulus_Pa`, `effective_density_kg_m3`, `mass_kg`,
`relative_stiffness`.

---

### `am_feature_checks`

Check minimum feature sizes and bridging span for a process.

**Input:** `process` (required); at least one of `wall_thickness_m`,
`hole_diameter_m`, `bridge_span_m`. All checks run; failures reported in
warnings (ok=True so all issues are visible).

**Returns:** `warnings` list with any failed checks, `all_pass`.

---

### `am_cost_rollup`

Total AM part cost from machine time, material, and post-processing.

**Input:** `process`, `material`, `build_time_s`, `support_volume_m3`,
`part_volume_m3` (all required); optional `machine_rate_per_h`,
`material_cost_per_kg`, `post_cost`, `fill_fraction`.

**Returns:** `machine_cost_usd`, `material_cost_usd`, `post_cost_usd`,
`total_cost_usd`.

---

### `am_nesting_packing`

Powder-bed nesting efficiency and batch throughput.

n_max_per_build = floor(build_volume × packing_factor / part_volume).

**Input:** `build_volume_m3`, `part_volume_m3`, `n_parts`; optional
`packing_factor` (default 0.60; SLS/MJF typically 0.55–0.70).

**Returns:** `n_max_per_build`, `batches_needed`, `utilisation`.

---

## Example

```
1. am_process_params  process:"SLS"
   → overhang_threshold: N/A (powder self-supports), min_wall: 0.7mm

2. am_build_time_estimate  process:"SLS"  bounding_box_m:[0.1,0.08,0.06]
   → layer_count:600, build_time_h:3.8

3. am_feature_checks  process:"FDM"  wall_thickness_m:0.0007  hole_diameter_m:0.002
   → warnings:["wall 0.7mm < FDM min 0.8mm"], all_pass:false

4. am_cost_rollup  process:"SLS"  material:"PA12"  build_time_s:13680
                   support_volume_m3:0  part_volume_m3:0.000050
   → total_cost_usd: 99.50
```
