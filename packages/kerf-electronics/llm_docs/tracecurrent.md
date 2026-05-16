# PCB Trace Current & Copper Thermal Design

IPC-2152 steady-state trace current capacity, required trace width,
DC resistance, via current and count, thermal via arrays, plane sheet
resistance, polygon-pour heatsink area, and copper busbar sizing.

## When to use

PCB trace current, trace ampacity, IPC-2152, trace width, copper weight,
1 oz copper, 2 oz copper, external trace, internal trace, temperature rise,
trace resistance, I²R loss, voltage drop, via current capacity, via count,
plated through-hole, via barrel, thermal via, thermal resistance, IPC-7093,
plane sheet resistance, Onderdonk fusing, polygon pour, copper pour heatsink,
copper busbar, busbar width, current density, PCB thermal management.

## Tools

### `tracecurrent_ipc2152`
IPC-2152 steady-state current capacity for a PCB trace.
Inputs: `width_mm`; optional `copper_oz`, `delta_t_c`, `layer` (external/internal), `k_pcb`, `t_pcb_mm`, `h_plane_mm`.
Returns `current_a`, `cross_section_mil2`, correction factors.

### `tracecurrent_required_width`
Bisection solver for trace width given a target current and allowable ΔT (IPC-2152 model, precision < 0.001 mm).
Inputs: `current_a`; optional `copper_oz`, `delta_t_c`, `layer`, `k_pcb`, `t_pcb_mm`, `h_plane_mm`.
Returns `width_mm`, `cross_section_mil2`.

### `tracecurrent_resistance`
PCB trace DC resistance, I²R power loss, and voltage drop with temperature coefficient of resistivity (IEC 60228).
Inputs: `width_mm`, `length_mm`; optional `copper_oz`, `current_a`, `temp_c`.
Returns `resistance_ohm`, `power_w`, `voltage_drop_v`, `sheet_resistance_ohm_sq`.

### `tracecurrent_via_capacity`
IPC-2152 current capacity of a plated through-hole via barrel (barrel annulus treated as equivalent trace).
Inputs: `drill_mm`; optional `plating_mm`, `delta_t_c`, `layer`.
Returns `current_a`, `barrel_area_mil2`.

### `tracecurrent_via_count`
Minimum number of parallel vias to carry a total current: n = ceil(I_total / I_per_via).
Inputs: `total_current_a`, `drill_mm`; optional `plating_mm`, `delta_t_c`, `layer`.
Returns `n_vias`, `current_per_via_a`.

### `tracecurrent_thermal_via`
Thermal via array Rθ and ΔT under a component pad (IPC-7093 parallel-barrel model with spreading resistance).
Inputs: `n_vias`, `drill_mm`; optional `plating_mm`, `t_pcb_mm`, `k_pcb`, `array_side_mm`, `power_w`.
Returns `rth_via_each_k_per_w`, `rth_array_k_per_w`, `rth_spread_k_per_w`, `rth_total_k_per_w`, `delta_t_k`.

### `tracecurrent_plane_rs`
Copper-plane sheet resistance [Ω/□] and optional current density with Onderdonk fusing cross-check.
Inputs: optional `copper_oz`, `temp_c`, `current_a`, `plane_width_mm`, `ambient_c`.
Returns `sheet_resistance_ohm_sq`, `thickness_mm`, and (when current given) `current_density_a_mm2`, `onderdonk_fuse_time_s`.

### `tracecurrent_pour_area`
Required copper-pour area [mm²/cm²] for a target PCB thermal resistance (1-D conduction model).
Inputs: `rth_target_k_per_w`; optional `t_pcb_mm`, `k_pcb`.
Returns `area_mm2`, `area_cm2`, `side_mm`.

### `tracecurrent_busbar`
Copper busbar width and resistance sized from current and maximum current density.
Inputs: `current_a`; optional `thickness_mm`, `j_max_a_mm2`, `length_mm`, `temp_c`.
Returns `width_mm`, `cross_section_mm2`, `resistance_ohm`, `power_w`, `voltage_drop_v`.

## Example

Find the IPC-2152 current capacity of a 2 mm wide external trace on 2 oz copper with 10 °C rise:

```json
{
  "tool": "tracecurrent_ipc2152",
  "width_mm": 2.0,
  "copper_oz": 2.0,
  "delta_t_c": 10,
  "layer": "external"
}
```
