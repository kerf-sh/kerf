# Switching DC-DC Converter Design

Kerf provides steady-state CCM design tools for the most common switching converter topologies: buck, boost, inverting buck-boost, isolated flyback, and SEPIC — plus a semiconductor junction-temperature estimator.

## When to use

Use these tools when you need to:
- Design a buck (step-down) converter: duty cycle, inductor, output cap, switch stress, efficiency
- Design a boost (step-up) converter with RHP-zero bandwidth warning
- Design an inverting buck-boost converter
- Design an isolated flyback converter: turns ratio, primary inductance, peak currents, RCD snubber note
- Design a SEPIC converter (non-inverting, buck or boost capable): dual inductors, coupling cap
- Estimate semiconductor junction temperature from power loss and thermal resistance
- Get CCM/DCM boundary, inductor ripple, component RMS currents, and conduction/switching losses

Trigger keywords: buck converter, boost converter, buck-boost, flyback converter, SEPIC, switching regulator, DC-DC converter, step-down, step-up, duty cycle, inductor design, output capacitor, CCM, DCM, switching loss, conduction loss, converter efficiency, RHP zero, flyback turns ratio, junction temperature, thermal resistance, Rth.

## Tools

| Tool | Purpose |
|---|---|
| `powerconv_buck_design` | CCM buck design: duty, L, C_out, switch/diode stress, losses, efficiency; inputs: v_in, v_out, i_out, fsw |
| `powerconv_boost_design` | CCM boost design with RHP-zero calculation; inputs: v_in, v_out, i_out, fsw |
| `powerconv_buck_boost_design` | CCM inverting buck-boost design; inputs: v_in, v_out_mag, i_out, fsw |
| `powerconv_flyback_design` | Isolated flyback: turns ratio, primary inductance, peak currents, switch/diode stress, RCD snubber note; inputs: v_in, v_out, i_out, fsw |
| `powerconv_sepic_design` | SEPIC CCM: dual L1=L2, coupling cap, switch peak current, switch stress; inputs: v_in, v_out, i_out, fsw |
| `powerconv_thermal` | Junction temperature from p_loss_w × rth_ja (or rth_jc + rth_cs + rth_sa); returns t_junction_c and over-temp flag |

## Example

**User ask:** "Design a 12 V → 5 V / 3 A buck converter switching at 400 kHz."

Call `powerconv_buck_design` with `v_in=12`, `v_out=5`, `i_out=3`, `fsw=400e3` → returns duty cycle, inductor value, output cap, switch/diode stress, and efficiency estimate.

To check the MOSFET won't overheat, follow up with `powerconv_thermal` using the returned `p_sw_cond_w + p_sw_switch_w` as `p_loss_w` and the device's `rth_ja` from its datasheet.
