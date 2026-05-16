# Classical Control Systems Analysis

Pure-Python classical control-theory tools. No OCC dependency. All tools are
stateless — they compute and return results; no DB write. Units: rad/s, seconds,
dimensionless gain.

---

## When to use

Use these tools when the conversation involves: PID tuning, control loop design,
step response, impulse response, damping ratio, overshoot, settling time, rise
time, Bode plot, gain margin, phase margin, Routh-Hurwitz stability, steady-state
error, root locus, transfer function, closed-loop performance, FOPDT process
model, Ziegler-Nichols, Cohen-Coon, IMC/Lambda tuning, first-order system,
second-order system, underdamped, overdamped, critically damped.

---

## Tools

### `controls_second_order_spec`

Compute second-order closed-loop performance specs from ωn and ζ.

**Input:** `wn` (rad/s, required), `zeta` (required)

**Returns:** peak overshoot %, time to first peak, 10%→90% rise time, 2% and 5%
settling times, damped natural frequency.

---

### `controls_second_order_inverse`

Inverse second-order spec: given one performance metric, compute ωn and ζ.

**Input:** exactly one of `overshoot` (%), `settling_time` (s), `rise_time` (s),
`peak_time` (s).

**Returns:** `wn`, `zeta`, warnings (metric alone does not uniquely fix both).

---

### `controls_first_order_response`

Compute first-order step and impulse response samples.
G(s) = K / (τs + 1).

**Input:** `K`, `tau` (s), `t_samples` (list of seconds), `response_type`
(`"step"` default or `"impulse"`).

**Returns:** time array and y array.

---

### `controls_second_order_response`

Compute second-order step and impulse response samples.
G(s) = K·ωn² / (s² + 2ζωn·s + ωn²).

**Input:** `wn`, `zeta`, `t_samples`, optional `K` (default 1.0),
`response_type` (`"step"` or `"impulse"`).

**Returns:** time array and y array for any damping regime.

---

### `controls_routh_hurwitz`

Routh-Hurwitz stability array and RHP pole count.

**Input:** `coeffs` — characteristic polynomial [a0, a1, ..., an],
highest-degree first.

**Returns:** full Routh array, number of sign changes in first column
(= RHP poles), `stable` flag.

---

### `controls_bode_point`

Bode magnitude (dB) and phase (deg) of G(s) = num(s)/den(s) at a single ω.

**Input:** `num`, `den` (polynomial coefficients, highest power first), `omega`
(rad/s).

**Returns:** `magnitude_dB`, `phase_deg`.

---

### `controls_gain_phase_margins`

Gain margin, phase margin, and crossover frequencies by numeric frequency sweep.

**Input:** `num`, `den` (open-loop TF), optional `omega_range`
([ωmin, ωmax] or [ωmin, ωmax, n_points]; default [0.001, 10000, 2000]).

**Returns:** `gain_margin_dB`, `phase_margin_deg`, `gain_crossover_rad_s`,
`phase_crossover_rad_s`, warnings (flags GM < 6 dB or PM < 30°).

---

### `controls_steady_state_errors`

Steady-state errors and error constants for unity-feedback system.

**Input:** `num_ol`, `den_ol` (open-loop TF).

**Returns:** `system_type` (number of free integrators), `Kp`, `Kv`, `Ka`,
`ess_step`, `ess_ramp`, `ess_parabolic`.

---

### `controls_pid_tuning`

PID controller tuning by four classical methods.

**Input:** `method` (required) — one of `"zn_open"`, `"zn_closed"`,
`"cohen_coon"`, `"imc"`.
- `zn_open`, `cohen_coon`: need `K`, `tau`, `theta` (FOPDT parameters).
- `zn_closed`: need `Ku`, `Tu` (ultimate gain/period).
- `imc`: need `K`, `tau`, `theta`, `lambda_c` (closed-loop time constant).

**Returns:** `Kp`, `Ti`, `Td`, `Ki`, `Kd` for P, PI, PD, and PID controllers.

---

### `controls_root_locus_breakaway`

Find real-axis breakaway and break-in points of the root locus.

**Input:** `num`, `den` (open-loop TF G(s)H(s)).

**Returns:** `breakaway_points` (real roots of d/ds[den/num] = 0), warnings.

---

## Example

```
1. controls_second_order_spec  wn:10  zeta:0.5
   → overshoot: 16.3%, settling_time_2pct: 0.80s, rise_time: 0.18s

2. controls_pid_tuning  method:"zn_open"  K:2.0  tau:5.0  theta:1.0
   → PID: Kp=1.5, Ti=2.0, Td=0.5

3. controls_gain_phase_margins  num:[1]  den:[1,3,2,0]
   → gain_margin_dB: 9.5, phase_margin_deg: 34.2, warnings: []
```
