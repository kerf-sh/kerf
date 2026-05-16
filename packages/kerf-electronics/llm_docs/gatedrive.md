# Gate Driver & Switching Loss Design

Power-switch gate-drive analysis: drive power, gate resistor selection, Miller
spurious-turn-on margin, switching/conduction/recovery losses, dead time,
bootstrap capacitor, and full thermal roll-up.

## When to use

MOSFET gate charge, IGBT gate driver, switching loss, conduction loss,
gate resistor, Miller plateau, spurious turn-on, dv/dt, dead time,
shoot-through, body diode, reverse recovery, Qrr, Rds(on), Vce(sat),
bootstrap cap, high-side driver, half-bridge, heatsink sizing, junction
temperature, SOA, Eon/Eoff, Psw, power stage, inverter, converter.

## Tools

### `gatedrive_gate_drive_power`
Computes average gate-drive current and driver power dissipation from
`qg_c`, `fsw_hz`, `vgs_drive_v`; supports negative `vgs_off_v`.
Returns `ig_avg_a`, `p_drive_w`, `vgs_swing_v`.

### `gatedrive_gate_resistor`
Selects external gate resistor for a target transition time.
Inputs: `vgs_drive_v`, `qg_c`, `t_transition_s`; optional `rg_internal_ohm`, `vgs_off_v`.
Returns `rg_total_ohm`, `rg_ext_ohm`, `ipeak_a`.

### `gatedrive_miller_spurious`
Miller-plateau dv/dt spurious-turn-on margin (Infineon AN-6076).
Inputs: `cgd_f`, `vgs_th_v`, `rg_off_ohm`, `vbus_v`; optional `t_rise_s`, `vgs_off_v`.
Returns `dvdt_critical_vps`, `spurious_risk`, `margin_ratio`.

### `gatedrive_switching_loss`
Switching energy (Eon, Eoff) and power from current/voltage overlap model.
Inputs: `vbus_v`, `i_load_a`, `t_on_s`, `t_off_s`, `fsw_hz`; optional Rg scaling.
Returns `eon_j`, `eoff_j`, `esw_total_j`, `psw_w`.

### `gatedrive_conduction_loss`
MOSFET (Rds(on)·Irms²) or IGBT (Vce_sat·I_avg) conduction loss.
Inputs: `device_type` (`mosfet`/`igbt`), `i_rms_a`, plus `rds_on_ohm` or `vce_sat_v`.
Returns `p_cond_w`, `formula`.

### `gatedrive_diode_recovery_loss`
Body/freewheeling diode reverse-recovery loss: P_rr = Qrr·Vbus·fsw.
Inputs: `qrr_c`, `vbus_v`, `fsw_hz`.
Returns `p_rr_w`, `e_rr_j`.

### `gatedrive_total_thermal`
Aggregates Psw + Pcond + Pdrive + Prr, computes Tj, and sizes heatsink.
Inputs: `p_sw_w`, `p_cond_w`; optional Rθjc/cs/sa, Tj_max, SOA Vds check.
Returns `p_total_w`, `tj_c`, `over_temp`, `r_th_sa_required`, `soa_ok`.

### `gatedrive_dead_time`
Minimum dead time from Coss and shoot-through / body-diode risk check.
Inputs: `coss_f`, `vbus_v`, `i_drive_a`; optional `t_dead_s`.
Returns `t_dead_min_s`, `shoot_through_risk`, `excessive_body_diode`.

### `gatedrive_bootstrap_cap`
High-side bootstrap capacitor sizing (Fairchild AN-6076).
Inputs: `qg_c`, `i_bias_a`, `fsw_hz`, `dv_max_v`; optional leakage and extra charge.
Returns `c_boot_f`, `q_total_c`.

## Example

Estimate drive power for a 100 nC MOSFET at 100 kHz with 15 V gate drive:

```json
{
  "tool": "gatedrive_gate_drive_power",
  "qg_c": 100e-9,
  "fsw_hz": 100000,
  "vgs_drive_v": 15
}
```

Then feed `p_drive_w` into `gatedrive_total_thermal` together with switching
and conduction losses to check junction temperature and size the heatsink.
