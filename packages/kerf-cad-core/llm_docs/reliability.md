# Reliability & Risk Engineering

Pure-Python reliability and risk analysis tools. No OCC dependency. All tools are stateless.
References: O'Connor & Kleyner, MIL-HDBK-217F, MIL-STD-1629A, IEC 60812, IEC 61025.

---

## When to use

Weibull analysis, Weibull fit, B10 life, B50 life, MTTF, MTBF, reliability function, hazard rate,
failure rate, exponential distribution, system reliability, series system, parallel system,
k-out-of-n, bridge network, availability, MTTR, redundancy, stress-strength interference,
FMEA, RPN, criticality, fault tree, cut sets, Birnbaum importance, reliability allocation, AGREE,
accelerated life testing, ALT, Arrhenius model, inverse power model, failure analysis.

---

## Tools

### `reliability_weibull_fit`

Fit a 2-parameter Weibull distribution to failure data (with optional censored/suspended units).
Methods: `'RRX'` (default), `'RRY'`, `'MLE'`.

**Input:** `times` (list, required), `censored` (list, optional), `method`, `gamma`

**Returns:** `beta` (shape), `eta` (scale/characteristic life), `R2`, warnings

---

### `reliability_weibull_b_life`

Weibull B-life: t_Bx = gamma + eta · (−ln(1−x))^(1/beta).

**Input:** `pct` (0–100, required), `beta` (required), `eta` (required), `gamma` (default 0)

**Returns:** `t_B` (same units as eta)

---

### `reliability_weibull_mttf`

Weibull MTTF and characteristic life. MTTF = gamma + eta · Γ(1 + 1/beta).

**Input:** `beta` (required), `eta` (required), `gamma` (default 0)

**Returns:** `mttf`, `t_632` (characteristic life at 63.2% failure)

---

### `reliability_weibull_eval`

Weibull reliability R(t), unreliability F(t), and hazard h(t) at time t.

**Input:** `t` (required), `beta` (required), `eta` (required), `gamma` (default 0)

**Returns:** `R`, `F`, `h`

---

### `reliability_exponential_mtbf_ci`

Chi-square confidence interval on MTBF from test data (homogeneous Poisson process).

**Input:** `failures` (integer, required), `test_time` (required), `confidence` (default 0.90)

**Returns:** `MTBF_lower`, `MTBF_upper`, `MTBF_point`, `R_at_MTBF_lower`

---

### `reliability_system`

System reliability for `'series'`, `'parallel'`, `'k_of_n'`, or `'bridge'` configurations.

**Input:** `config` (required), plus:
- `'series'`/`'parallel'`/`'bridge'`: `reliabilities` (list)
- `'k_of_n'`: `k`, `n`, `r`

**Returns:** `R_system`

---

### `reliability_availability`

Steady-state availability A = MTBF / (MTBF + MTTR). Optionally computes redundancy gain.

**Input:** `mtbf` (required), `mttr` (required), `r` (optional), `n_active`, `n_standby`

**Returns:** `availability`, optionally `redundancy` with `R_active`, `gain_active`, `R_with_standby`

---

### `reliability_stress_strength`

Stress-strength interference reliability.

**Modes:**
- `'normal'`: closed-form P(strength > stress) for normal distributions; inputs `mu_s`, `sigma_s`, `mu_r`, `sigma_r`
- `'numeric'`: empirical; inputs `stress_samples`, `strength_samples` (lists)

**Returns:** `R` (reliability)

---

### `reliability_fmea_rpn`

FMEA Risk Priority Number: RPN = Severity × Occurrence × Detection (each 1–10).
Risk levels: low (<50), medium (50–99), high (100–199), critical (≥200).

**Input:** `severity` (int, required), `occurrence` (int, required), `detection` (int, required),
`mode_ratio` (default 1.0)

**Returns:** `RPN`, `risk_level`, `criticality`

---

### `reliability_fault_tree`

Fault-tree top-event probability, minimal cut sets, and Birnbaum importance.

**Input:** `tree` (nested dict with `type`:`AND`/`OR`/`basic`/`K_OF_N`, required),
`event_id` (optional, for Birnbaum importance)

**Returns:** `p_top`, `cut_sets`, `n_cut_sets`, `I_birnbaum` (if event_id given)

---

### `reliability_allocation`

Allocate system reliability target to components.

**Methods:** `'equal'` (r_i = r_sys^(1/n)) or `'agree'` (AGREE proportional to importance).

**Input:** `r_system` (required), `method` (default `'equal'`), `n_components` (equal),
`importances` (agree), `n_i`, `t_i`

**Returns:** per-component `target_reliability` and `failure_rate`

---

### `reliability_accel_life`

Acceleration factor for accelerated life testing (ALT).

**Models:**
- `'arrhenius'`: AF = exp(E_a/k · (1/T_use − 1/T_acc)); inputs `E_a`, `T_use_K`, `T_acc_K`
- `'inverse_power'`: AF = (V_acc/V_use)^n; inputs `V_use`, `V_acc`, `n`

**Returns:** `AF`, `equivalent_life_multiplier`

---

## Example

```
1. reliability_weibull_fit  times:[1200,1450,1600,1800,2200]
   → beta:2.1  eta:1800  R2:0.97

2. reliability_weibull_b_life  pct:10  beta:2.1  eta:1800
   → t_B10: 780 hours

3. reliability_system  config:"series"  reliabilities:[0.95,0.98,0.99]
   → R_system: 0.921

4. reliability_fmea_rpn  severity:8  occurrence:4  detection:6
   → RPN:192  risk_level:"high"
```
