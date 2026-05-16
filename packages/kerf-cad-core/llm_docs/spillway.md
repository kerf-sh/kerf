# Spillway and Dam Hydraulics

Pure-Python spillway and dam hydraulics: WES ogee crest discharge and profile, gated orifice, chute normal depth, USBR stilling basin design, energy dissipation, scour depth estimation, modified-Puls flood routing, freeboard (wave setup + runup), and gravity dam stability. No OCC dependency. All tools are stateless and never raise. Units: SI (metres, m³/s). References: USBR Design of Small Dams (1977), USACE EM 1110-2-1601, Chaudhry (2008).

---

## When to use

Use these tools for dam and spillway hydraulic design: ogee (overflow) spillway discharge and crest shape, gate/orifice discharge (sluice, radial, drum gates), spillway chute normal depth and terminal velocity, stilling basin type selection (USBR Type I–IV) and length, hydraulic jump sequent depth, energy dissipation at spillway toe, downstream scour depth (Lacey alluvial or Mason plunge pool), level-pool flood routing (modified Puls), reservoir wave setup and freeboard, gravity dam overturning/sliding/uplift/middle-third stability.

---

## Tools

### `spillway_ogee_discharge`

WES ogee (overflow) spillway discharge: Q = C·L_eff·He^1.5. Automatically corrects C for head ratio, approach velocity, end contractions, and submergence (Villemonte 1947).

**Input:** `design_head_m`, `actual_head_m`, `crest_length_m` (required); `approach_depth_m`, `num_end_contractions` (0/1/2), `tailwater_m`, `C0` (optional, default 2.21 SI). **Returns:** `discharge_m3s`, `C_effective`, `L_eff_m`, `He_m`, `submergence_ratio`, `warnings`.

---

### `spillway_ogee_crest_profile`

(x, y) coordinate table of WES standard ogee crest. Downstream: y/Hd = −0.5·(x/Hd)^1.85; upstream: circular-arc approximation.

**Input:** `design_head_m` (required); `n_upstream` (default 10), `n_downstream` (default 40) (optional). **Returns:** `design_head_m`, `profile` (list of `{x_m, y_m}`).

---

### `spillway_orifice_discharge`

Gated or submerged orifice discharge. Free-flow: Q = Cd·a·W·sqrt(2g·(Hu − a/2)); submerged: uses (Hu − Hd).

**Input:** `gate_opening_m`, `gate_width_m`, `head_upstream_m` (required); `head_downstream_m`, `Cd` (default 0.61), `gate_type` (`sluice`/`radial`/`drum`) (optional). **Returns:** `discharge_m3s`, `velocity_m_s`, `flow_condition` (`free`/`submerged`/`reverse`), `warnings`.

---

### `spillway_chute_velocity`

Normal depth and terminal velocity in a rectangular spillway chute (Manning's equation, solved by bisection). Optionally estimates downstream velocity via energy conservation over chute length.

**Input:** `flow_m3s`, `chute_width_m`, `chute_slope`, `manning_n` (required); `chute_length_m` (optional). **Returns:** `normal_depth_m`, `terminal_velocity_m_s`, `froude_number`, `flow_area_m2`, `hydraulic_radius_m`, `downstream_velocity_m_s` (if length provided), `warnings`.

---

### `spillway_stilling_basin`

USBR stilling basin design: Froude number Fr1, sequent depth y2 (Bélanger), basin type (I/II/III/IV/undular), basin length, end-sill height, and tailwater match check.

**Input:** `upstream_depth_m`, `flow_m3s`, `chute_width_m`, `tailwater_depth_m` (required); `elevation_drop_m` (optional). **Returns:** `Fr1`, `y2_m`, `basin_type`, `basin_length_m`, `end_sill_height_m`, `warnings`.

---

### `spillway_energy_dissipation`

Energy at spillway toe and required apron length: E_toe = y_ds + V_toe²/(2g); apron = basin + downstream protection (USBR 6·y2 rule).

**Input:** `upstream_head_m`, `downstream_depth_m`, `flow_m3s`, `basin_width_m` (required); `basin_roughness_n` (optional, default 0.015). **Returns:** `energy_at_toe_m`, `velocity_at_toe_m_s`, `froude_at_toe`, `apron_length_m`, `basin_length_m`, `downstream_protection_length_m`, `warnings`.

---

### `spillway_scour_depth`

Downstream scour depth estimate. `lacey` method (alluvial regime): d_s = 0.47·(Q/f)^(1/3). `mason` method (plunge pool): d_s = 1.9·Q^0.6·H^0.5/d50^0.06.

**Input:** `flow_m3s`, `channel_width_m`, `d50_mm` (required); `method` (`lacey` default or `mason`), `head_drop_m` (required for mason) (optional). **Returns:** `scour_depth_m`, `method`, `unit_discharge_m2s`, `lacey_silt_factor`, `warnings`.

---

### `spillway_flood_routing_puls`

Level-pool reservoir flood routing via modified-Puls method. Routes an inflow hydrograph through a reservoir given the storage-discharge table.

**Input:** `inflow_hydrograph` (list of [t_s, I_m3s] pairs), `storage_discharge_pairs` (list of [S_m3, Q_m3s] pairs), `dt_s` (routing time step, s) — all required; `initial_storage_m3` (optional, default 0). **Returns:** `outflow_hydrograph` (list of {t_s, outflow_m3s, storage_m3}), `peak_outflow_m3s`, `peak_outflow_time_s`, `attenuation_m3s`.

---

### `spillway_dam_freeboard`

Required dam freeboard from wind wave setup and runup: significant wave height (Bretschneider/SMB), wind setup, wave runup, and safety margin.

**Input:** `reservoir_fetch_km`, `wind_speed_m_s`, `dam_height_m` (required); `reservoir_depth_m` (default 10), `embankment_slope_v_to_h` (H:V, default 3), `freeboard_safety_m` (default 0.5) (optional). **Returns:** `significant_wave_height_m`, `wave_period_s`, `wind_setup_m`, `wave_runup_m`, `required_freeboard_m`, `warnings`.

---

### `spillway_gravity_dam_stability`

Gravity dam stability per USBR/ICOLD: overturning FOS (≥ 1.5), uplift, sliding FOS, and middle-third eccentricity check. Per-unit-length analysis, simplified rectangular section.

**Input:** `dam_height_m`, `dam_base_width_m`, `upstream_water_depth_m` (required); `concrete_density_kg_m3` (default 2400), `downstream_water_depth_m`, `uplift_fraction`, `friction_coefficient`, `unit_length_m`, `crest_width_m` (optional). **Returns:** `weight_kN`, `uplift_kN`, `FOS_overturning`, `FOS_sliding`, `eccentricity_m`, `middle_third_ok`, `stable`, `warnings`.

---

## Example

```
1. spillway_ogee_discharge
     design_head_m:3.0  actual_head_m:2.5  crest_length_m:20
   → discharge_m3s: 87.5

2. spillway_chute_velocity
     flow_m3s:87.5  chute_width_m:10  chute_slope:0.2  manning_n:0.015
   → normal_depth_m:0.42  terminal_velocity_m_s:20.8  froude_number:10.2

3. spillway_stilling_basin
     upstream_depth_m:0.42  flow_m3s:87.5  chute_width_m:10  tailwater_depth_m:5.5
   → Fr1:10.2  y2_m:5.8  basin_type:"Type III"  basin_length_m:28

4. spillway_gravity_dam_stability
     dam_height_m:20  dam_base_width_m:16  upstream_water_depth_m:18
   → FOS_overturning:2.1  FOS_sliding:1.8  stable:true
```
