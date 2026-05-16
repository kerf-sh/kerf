# Building Plumbing Engineering

Pure-Python building plumbing module covering supply-pipe sizing, drain/vent
sizing, hot water, recirculation, storm drainage, water hammer, and expansion
tanks. References IPC 2021, Hunter (1940 BMS 65), ASHRAE Applications Ch. 50,
and PDI WH-201.

---

## When to use

Reach for this module when the user asks about:

- converting fixture units (WSFU) to design flow using the Hunter curve
- sizing cold-water supply pipes from demand, pressure, and pipe length
- sizing drainage pipes (horizontal branch, stack, building drain) from DFU
- vent pipe sizing from DFU and developed vent length
- trap-arm length and slope compliance (IPC §1002.1)
- drain slope and full/half-flow capacity (Manning's equation)
- sizing a storage water heater (ASHRAE occupancy method)
- hot-water recirculation loop flow, heat loss, and pump head
- roof storm drain and leader sizing from rainfall intensity
- selecting a water hammer arrestor (PDI WHA size) for a branch
- sizing a closed-system diaphragm expansion tank

---

## Tools

### `plumbing_hunter_demand`

Convert total supply fixture units (WSFU) to design demand flow (GPM) using
the Hunter probability curve (BMS 65 / IPC Appendix E).
Inputs: `fixture_units` (required); optional `system_type`
(flush_tank/flush_valve, default flush_tank).
Returns: `demand_gpm`.

### `plumbing_size_supply_pipe`

Select minimum NPS for a cold-water supply pipe given demand flow and available
pressure budget. Uses Hazen-Williams (C=150 copper/plastic). Enforces IPC
§604.3 velocity limit.
Inputs: `demand_gpm`, `available_pressure_psi`, `pipe_length_ft` (required);
optional `elevation_diff_ft`, `meter_loss_psi`, `residual_pressure_psi`,
`material` (copper_l/cpvc/pex/galvanized/cast_iron), `velocity_limit_fps`.
Returns: `pipe_nps`, `velocity_fps`, `pressure_loss_psi`, `residual_psi`,
`warnings`.

### `plumbing_dfu_drain_size`

Select minimum drainage pipe NPS for a given DFU load per IPC Table 710.1.
Inputs: `dfu` (required); optional `pipe_type`
(horizontal_branch/building_drain/stack, default horizontal_branch).
Returns: `pipe_nps_in`.

### `plumbing_vent_size`

Select minimum vent pipe NPS per IPC Table 906.2, satisfying both the DFU
served and the developed vent length simultaneously.
Inputs: `dfu_served`, `developed_length_ft` (both required).
Returns: `vent_nps_in`.

### `plumbing_trap_arm_slope`

Check trap-arm length and slope compliance per IPC §1002.1. Flags arm too long
or slope outside the 1/8"–1/2" per foot range.
Inputs: `trap_arm_length_ft`, `trap_size_nps` (required); optional
`slope_in_per_ft` (default 0.25).
Returns: `max_length_ft`, `arm_ok`, `slope_ok`, `warnings`.

### `plumbing_drain_slope_manning`

Compute full-flow and half-flow drain capacity using Manning's equation.
Flags slope below IPC §704.1 minimum (1/4"/ft for ≤ 3"; 1/8"/ft for ≥ 4").
Inputs: `pipe_nps`, `slope_in_per_ft` (required); optional `n_manning`
(default 0.013 PVC/ABS DWV).
Returns: `full_flow_gpm`, `half_flow_gpm`, `full_flow_fps`, `slope_ok`.

### `plumbing_hot_water_heater`

Size a storage water heater using ASHRAE Applications Chapter 50
occupancy-based daily demand and peak-hour fractions.
Occupancy types: apartment, dormitory, motel, hotel, office, restaurant,
school_elem, school_high, hospital.
Inputs: `occupancy_type`, `num_units` (required); optional `inlet_temp_f`,
`supply_temp_f`, `recovery_efficiency`, `fuel_btu_hr`.
Returns: `peak_hourly_demand_gal`, `recovery_rate_gph`, `required_btu_hr`,
`storage_volume_gal`, `warnings`.

### `plumbing_hw_recirc_loop`

Size a hot-water recirculation loop: minimum pump flow, pipe heat loss, and
pump head per ASHRAE Applications §50.6.
Inputs: `loop_length_ft`, `pipe_nps` (required); optional `supply_temp_f`,
`ambient_temp_f`, `insulation_r_value`.
Returns: `recirc_flow_gpm`, `heat_loss_btu_hr`, `pump_head_ft`, `warnings`.

### `plumbing_storm_drain_leader`

Size roof storm drain leaders and horizontal storm drains from rainfall
intensity × roof area per IPC Tables 1106.2/1106.3.
Design flow: Q (gpm) = roof_area_ft² × rainfall_in_hr / 96.23.
Inputs: `roof_area_ft2`, `rainfall_rate_in_hr` (required); optional
`leader_type` (vertical/horizontal, default vertical).
Returns: `design_flow_gpm`, `leader_nps_in`.

### `plumbing_water_hammer_arrestor`

Select a water hammer arrestor (WHA) PDI size letter per PDI WH-201.
Sizes A–F correspond to fixture unit ranges 1–329+ FU on the branch.
Install at branches with quick-closing valves (solenoid, flush valves,
washing machines).
Inputs: `fixture_units` (required); optional `location` (label).
Returns: `pdi_size`, `max_fixture_units`, `multiple_units_required`.

### `plumbing_expansion_tank`

Size a diaphragm-type expansion tank for a closed water-heater system per
ASHRAE Applications §50.7 / ASME A112.4.3M.
Inputs: `system_water_volume_gal` (required); optional `supply_temp_f`,
`cold_fill_temp_f`, `system_pressure_psi`, `relief_valve_psi`.
Returns: `tank_volume_gal`, `acceptance_volume_gal`, `warnings`.

---

## Example

**User ask:** "A 20-unit apartment has 5 WSFU per unit flush-tank system.
The water heater supply is 120°F. Size the supply main (80 psi static, 60 ft
developed length, ground floor) and the expansion tank for 150 gal of system
water."

1. `plumbing_hunter_demand` — fixture_units: 100, system_type: flush_tank
   → demand_gpm
2. `plumbing_size_supply_pipe` — demand_gpm from step 1,
   available_pressure_psi: 80, pipe_length_ft: 60
   → pipe_nps
3. `plumbing_expansion_tank` — system_water_volume_gal: 150,
   supply_temp_f: 120
   → tank_volume_gal

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Tools are **stateless** — validate and return dicts; no DB writes.
- Invalid inputs return `{ok: false, reason: "..."}` — never raise.
