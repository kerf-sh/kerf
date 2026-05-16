# Battery Pack Sizing and Runtime

Pure-Python battery pack tools: cell configuration sizing, Peukert-corrected runtime, CC-CV charge time, and thermal rise — all in a single combined report if needed.

## When to use

Use these tools when you need to:
- Determine how many cells to put in series and parallel to hit a target voltage and capacity
- Estimate how long a battery pack will run under a multi-step load profile with Peukert correction and depth-of-discharge limits
- Estimate how long it takes to recharge a depleted pack using a CC-CV charger
- Get a combined sizing + runtime + charge + thermal report in one call
- Check C-rate warnings, mass, volume, and energy figures for a Li-ion or lead-acid pack

Trigger keywords: battery pack, cell configuration, series parallel cells, pack voltage, pack capacity, runtime, Peukert, depth of discharge, DoD, charge time, CC-CV, Li-ion, 18650, energy density, thermal rise, battery report.

## Tools

| Tool | Purpose |
|---|---|
| `battery_size_pack` | Computes n_series, n_parallel, total cells, pack voltage/capacity/energy, mass, and volume from target_voltage_v, target_capacity_ah, cell_voltage_v, cell_capacity_ah |
| `battery_runtime` | Estimates runtime over a multi-step load_profile using Peukert correction (peukert_k) and DoD limit; returns per-step duration, total runtime, energy, and exhausted flag |
| `battery_charge_time` | Estimates CC-CV charge time from pack_capacity_ah, charge_c_rate, and dod_at_start; returns cc_time_h, cv_tail_h, total_time_h |
| `battery_report` | Combined report: sizing + runtime + charge time + adiabatic thermal rise in one call; accepts full cell spec and load_profile |

## Example

**User ask:** "I need a 24 V / 10 Ah pack using 3.6 V / 3 Ah 18650 cells. How long will it run a 50 W constant load, and how long to recharge at 1C?"

1. Call `battery_size_pack` with `target_voltage_v=24`, `target_capacity_ah=10`, `cell_voltage_v=3.6`, `cell_capacity_ah=3` → get n_series, n_parallel, pack specs.
2. Use `battery_report` with load_profile `[{"power_W": 50, "duration_s": 36000}]` → get runtime, charge time, and thermal rise in one call.
