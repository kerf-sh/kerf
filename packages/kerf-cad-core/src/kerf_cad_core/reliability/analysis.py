"""
kerf_cad_core.reliability.analysis — systems reliability & risk analysis (pure Python).

Implements the following public functions:

Weibull distribution (2-parameter and 3-parameter)
  weibull_reliability(t, beta, eta, *, gamma)
      R(t) = exp(-((t-gamma)/eta)^beta)
  weibull_hazard(t, beta, eta, *, gamma)
      h(t) = (beta/eta) * ((t-gamma)/eta)^(beta-1)
  weibull_b_life(pct, beta, eta, *, gamma)
      B-life t_B such that F(t_B) = pct/100 (e.g. B10, B50)
  weibull_mttf(beta, eta, *, gamma)
      MTTF = gamma + eta * Gamma(1 + 1/beta)
  weibull_characteristic_life(beta, eta, *, gamma)
      Characteristic life = eta (63.2% failure point); returned directly.
  weibull_fit(times, *, censored, method, gamma)
      Fit Weibull parameters from failure (and right-censored) data.
      Supports rank-regression (RRX, RRY) and MLE.

Exponential distribution
  exponential_reliability(t, mtbf)
      R(t) = exp(-t/mtbf)
  exponential_mtbf_ci(failures, test_time, *, confidence)
      Chi-square bounds on MTBF from observed failures and test time.

System reliability
  system_series(reliabilities)
      R_s = product(R_i)
  system_parallel(reliabilities)
      R_s = 1 - product(1 - R_i)
  system_k_out_of_n(k, n, r)
      Binomial k-out-of-n: R = sum_{i=k}^{n} C(n,i)*r^i*(1-r)^(n-i)
  system_bridge(r_list)
      5-component bridge via event-decomposition.
  availability(mtbf, mttr)
      A = MTBF / (MTBF + MTTR)
  redundancy_gain(r, n_active, n_standby)
      Reliability improvement from active or standby redundancy.

Stress-strength interference
  stress_strength_normal(mu_s, sigma_s, mu_r, sigma_r)
      Closed-form P(R > S) for normal-normal: R = phi(z), z = (mu_r-mu_s)/sqrt(sigma_r^2+sigma_s^2)
  stress_strength_numeric(stress_samples, strength_samples)
      Monte-Carlo / empirical: fraction of pairs where strength > stress.

FMEA
  fmea_rpn(severity, occurrence, detection)
      RPN = S × O × D  (each 1-10)
  fmea_criticality(severity, occurrence, *, mode_ratio)
      Criticality Cm = beta_m * alpha_t * lambda_p * t

Fault tree
  fault_tree_top(tree)
      Evaluate top-event probability from nested dict tree (AND/OR/k-of-n).
  fault_tree_cut_sets(tree)
      Enumerate minimal cut sets by Boolean reduction.
  fault_tree_importance(tree, event_id)
      Birnbaum importance I_B(i) = dR_sys/dR_i via numerical perturbation.

Reliability allocation
  reliability_allocation_equal(r_system, n_components)
      Equal apportionment: r_i = r_sys^(1/n)
  reliability_allocation_agree(r_system, importances, *, n_i, t_i, lambda_g)
      AGREE method: allocate based on subsystem importance and complexity.

Accelerated life testing
  arrhenius_af(E_a, T_use_K, T_acc_K)
      Arrhenius acceleration factor AF = exp(E_a/k * (1/T_use - 1/T_acc))
  inverse_power_af(V_use, V_acc, n)
      Inverse power law: AF = (V_acc/V_use)^n

All functions return plain dicts:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<message>"}

Functions NEVER raise. Warnings are issued via the `warnings` module
and also collected in the result's "warnings" list.

Units
-----
  time             — any consistent unit (hours, cycles, years)
  probability/R    — dimensionless [0, 1]
  temperature      — Kelvin for Arrhenius
  activation_energy — eV (electron-volts) for Arrhenius

References
----------
O'Connor & Kleyner, "Practical Reliability Engineering", 5th ed., Wiley 2012
Tobias & Trindade, "Applied Reliability", 3rd ed., CRC Press 2012
MIL-HDBK-217F, "Reliability Prediction of Electronic Equipment"
IEC 60812:2018 — FMEA procedure
IEC 61025:2006 — Fault tree analysis

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Boltzmann constant (eV/K) for Arrhenius
# ---------------------------------------------------------------------------
_K_BOLTZMANN_EV = 8.617333262145e-5  # eV/K


# ---------------------------------------------------------------------------
# Numeric helpers — erf/erfc implemented without scipy
# ---------------------------------------------------------------------------

def _erf(x: float) -> float:
    """Abramowitz & Stegun approximation to erf(x), max error < 1.5e-7."""
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = (((( 1.061405429 * t
                - 1.453152027) * t
               + 1.421413741) * t
              - 0.284496736) * t
             + 0.254829592) * t
    return sign * (1.0 - poly * math.exp(-x * x))


def _erfc(x: float) -> float:
    return 1.0 - _erf(x)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF Phi(x)."""
    return 0.5 * _erfc(-x / math.sqrt(2.0))


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (rational approximation, Beasley-Springer-Moro)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p must be in (0,1), got {p}")
    if p == 0.5:
        return 0.0

    # Rational approximation — accurate to ~1e-9
    a = [0.0, -3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [0.0, -5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]

    p_lo = 0.02425
    p_hi = 1.0 - p_lo

    if p < p_lo:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    elif p <= p_hi:
        q = p - 0.5
        r = q * q
        return (((((a[1]*r+a[2])*r+a[3])*r+a[4])*r+a[5])*r+a[6])*q / \
               (((((b[1]*r+b[2])*r+b[3])*r+b[4])*r+b[5])*r+1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)


def _gamma_func(x: float) -> float:
    """
    Gamma function via Lanczos approximation (g=7, n=9).
    Accurate to ~1e-9 for x > 0.
    """
    if x < 0.5:
        return math.pi / (math.sin(math.pi * x) * _gamma_func(1.0 - x))
    x -= 1.0
    g = 7
    p = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
         771.32342877765313, -176.61502916214059, 12.507343278686905,
         -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]
    t = x + g + 0.5
    s = sum(p[i] / (x + i) for i in range(1, len(p)))
    s += p[0]
    return math.sqrt(2 * math.pi) * t ** (x + 0.5) * math.exp(-t) * s


def _chi2_ppf(p: float, df: int) -> float:
    """
    Chi-squared inverse CDF (quantile) via Wilson-Hilferty approximation.
    Good for df >= 1, p in (0, 1).
    """
    z = _norm_ppf(p)
    k = float(df)
    h = 2.0 / (9.0 * k)
    x = k * (1.0 - h + z * math.sqrt(h)) ** 3
    return max(x, 1e-12)


def _ln_gamma(x: float) -> float:
    return math.log(_gamma_func(x))


def _log_factorial(n: int) -> float:
    return sum(math.log(i) for i in range(2, n + 1))


def _comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return 0.0
    return math.exp(_log_factorial(n) - _log_factorial(k) - _log_factorial(n - k))


# ---------------------------------------------------------------------------
# Input guards
# ---------------------------------------------------------------------------

def _guard_prob(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v) or v < 0.0 or v > 1.0:
        return f"{name} must be in [0, 1], got {value!r}"
    return None


def _warn_and_collect(msg: str, bucket: list) -> None:
    warnings.warn(msg, stacklevel=4)
    bucket.append(msg)


# ===========================================================================
# Weibull distribution
# ===========================================================================

def weibull_reliability(
    t: float,
    beta: float,
    eta: float,
    *,
    gamma: float = 0.0,
) -> dict:
    """
    Weibull reliability (survival) function.

    R(t) = exp(-((t - gamma) / eta)^beta)

    Parameters
    ----------
    t     : time (must be > gamma)
    beta  : shape parameter (> 0).  beta < 1 → infant mortality; beta = 1 →
            exponential; beta > 1 → wear-out.
    eta   : scale / characteristic life (> 0)
    gamma : location (minimum life) parameter (default 0).

    Returns
    -------
    {"ok": True, "R": float, "F": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("beta", beta), ("eta", eta)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}
    t = float(t)
    gamma = float(gamma)
    if t <= gamma:
        return {"ok": False, "reason": f"t must be > gamma ({gamma}), got {t}"}

    z = (t - gamma) / float(eta)
    R = math.exp(-(z ** float(beta)))
    F = 1.0 - R
    if R < 0.1:
        _warn_and_collect(
            f"weibull_reliability: low reliability R={R:.4f} at t={t}", warns
        )
    return {"ok": True, "R": R, "F": F, "warnings": warns}


def weibull_hazard(
    t: float,
    beta: float,
    eta: float,
    *,
    gamma: float = 0.0,
) -> dict:
    """
    Weibull hazard (instantaneous failure) rate.

    h(t) = (beta / eta) * ((t - gamma) / eta)^(beta - 1)

    Returns
    -------
    {"ok": True, "h": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("beta", beta), ("eta", eta)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}
    t = float(t)
    gamma = float(gamma)
    if t <= gamma:
        return {"ok": False, "reason": f"t must be > gamma ({gamma}), got {t}"}

    beta = float(beta)
    eta = float(eta)
    z = (t - gamma) / eta
    h = (beta / eta) * z ** (beta - 1.0)
    return {"ok": True, "h": h, "warnings": warns}


def weibull_b_life(
    pct: float,
    beta: float,
    eta: float,
    *,
    gamma: float = 0.0,
) -> dict:
    """
    Weibull B-life: time at which pct% of the population has failed.

    t_Bx = gamma + eta * (-ln(1 - x))^(1/beta)   where x = pct/100

    Common: B10 (pct=10), B50 (pct=50).

    Returns
    -------
    {"ok": True, "t_B": float, "pct": float, "warnings": [...]}
    """
    warns: list[str] = []
    if not (0 < pct < 100):
        return {"ok": False, "reason": f"pct must be in (0, 100), got {pct}"}
    for name, val in (("beta", beta), ("eta", eta)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}

    F = pct / 100.0
    t_B = float(gamma) + float(eta) * (-math.log(1.0 - F)) ** (1.0 / float(beta))
    if t_B < 0:
        _warn_and_collect(f"weibull_b_life: computed t_B={t_B:.4g} < 0", warns)
    return {"ok": True, "t_B": t_B, "pct": pct, "warnings": warns}


def weibull_mttf(
    beta: float,
    eta: float,
    *,
    gamma: float = 0.0,
) -> dict:
    """
    Weibull MTTF (mean time to failure).

    MTTF = gamma + eta * Gamma(1 + 1/beta)

    Returns
    -------
    {"ok": True, "mttf": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("beta", beta), ("eta", eta)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}

    mttf = float(gamma) + float(eta) * _gamma_func(1.0 + 1.0 / float(beta))
    return {"ok": True, "mttf": mttf, "warnings": warns}


def weibull_characteristic_life(
    beta: float,
    eta: float,
    *,
    gamma: float = 0.0,
) -> dict:
    """
    Weibull characteristic life (scale parameter).

    The characteristic life is eta + gamma, i.e. the time at which 63.2% of
    units have failed: F(eta + gamma) = 1 - exp(-1) ≈ 0.6321.

    Returns
    -------
    {"ok": True, "eta": float, "t_632": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("beta", beta), ("eta", eta)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}

    t_632 = float(gamma) + float(eta)  # F(t_632) = 1 - 1/e ≈ 0.6321
    return {"ok": True, "eta": float(eta), "t_632": t_632, "warnings": warns}


def weibull_fit(
    times: list,
    *,
    censored: list | None = None,
    method: str = "RRX",
    gamma: float = 0.0,
) -> dict:
    """
    Fit a 2-parameter Weibull distribution to failure time data.

    Supports right-censored data (suspend times) via median-rank regression
    or MLE.

    Parameters
    ----------
    times    : list of failure times (all > gamma, all > 0)
    censored : list of right-censored (suspension) times (default None → no
               censoring).  Each value is a time at which a unit was removed
               without failing.
    method   : "RRX" (regression on X, default), "RRY", or "MLE"
    gamma    : known location parameter (default 0); set to 0 for standard
               2-parameter Weibull.

    Returns
    -------
    {"ok": True, "beta": float, "eta": float, "gamma": float,
     "r_squared": float (for regression methods), "warnings": [...]}
    """
    warns: list[str] = []
    if not times:
        return {"ok": False, "reason": "times must be a non-empty list"}
    if method not in ("RRX", "RRY", "MLE"):
        return {"ok": False, "reason": f"method must be 'RRX', 'RRY', or 'MLE', got {method!r}"}
    if err := _guard_nonneg("gamma", gamma):
        return {"ok": False, "reason": err}

    gamma = float(gamma)
    fail_times = []
    for i, t in enumerate(times):
        try:
            v = float(t)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"times[{i}] is not a number: {t!r}"}
        if v <= gamma:
            return {"ok": False, "reason": f"times[{i}]={v} must be > gamma={gamma}"}
        fail_times.append(v)

    susp_times: list[float] = []
    if censored:
        for i, t in enumerate(censored):
            try:
                v = float(t)
            except (TypeError, ValueError):
                return {"ok": False, "reason": f"censored[{i}] is not a number: {t!r}"}
            if v <= gamma:
                return {"ok": False, "reason": f"censored[{i}]={v} must be > gamma={gamma}"}
            susp_times.append(v)

    n_f = len(fail_times)
    if n_f < 2:
        _warn_and_collect(
            "weibull_fit: fewer than 2 failure times — estimates unreliable", warns
        )

    # ---- Median rank (Benard approximation) with adjusted ranks for censoring ----
    # Build combined event list: (time, is_failure)
    events: list[tuple[float, bool]] = (
        [(t, True) for t in fail_times] + [(t, False) for t in susp_times]
    )
    events.sort(key=lambda e: e[0])

    N_total = len(events)
    fail_ranks: list[float] = []
    fail_xs: list[float] = []    # log(t - gamma)
    fail_ys: list[float] = []    # log(-log(1 - F))

    i_prev = 0.0  # adjusted order number of previous failure
    k = 0  # count of failures seen so far
    n_remaining = N_total

    for ev_idx, (t_ev, is_fail) in enumerate(events):
        if is_fail:
            # Adjusted rank (Nelson / Johnson reverse order)
            # i_j = i_{j-1} + (N+1 - i_{j-1}) / (N - ev_idx + 1)  [Abernethy]
            increment = (N_total + 1 - i_prev) / (N_total - ev_idx + 1)
            i_prev = i_prev + increment
            fail_ranks.append(i_prev)
            F_j = (i_prev - 0.3) / (N_total + 0.4)  # Benard median rank
            F_j = max(1e-9, min(1.0 - 1e-9, F_j))
            x = math.log(t_ev - gamma)
            y = math.log(-math.log(1.0 - F_j))
            fail_xs.append(x)
            fail_ys.append(y)

    if len(fail_xs) < 2:
        return {"ok": False, "reason": "Need at least 2 failure events to fit Weibull"}

    if method in ("RRX", "RRY"):
        # Linearised Weibull: Y = beta*X - beta*ln(eta)
        # X = ln(t), Y = ln(-ln(1-F))  → linear regression
        n = len(fail_xs)
        sx = sum(fail_xs)
        sy = sum(fail_ys)
        sxx = sum(xi * xi for xi in fail_xs)
        sxy = sum(xi * yi for xi, yi in zip(fail_xs, fail_ys))

        if method == "RRX":
            # Regress Y on X (minimise X residuals — standard for reliability)
            denom = n * sxx - sx * sx
            if abs(denom) < 1e-30:
                return {"ok": False, "reason": "Degenerate fit: all times identical"}
            beta_hat = (n * sxy - sx * sy) / denom
            intercept = (sy - beta_hat * sx) / n
        else:  # RRY — regress X on Y
            syy = sum(yi * yi for yi in fail_ys)
            denom = n * syy - sy * sy
            if abs(denom) < 1e-30:
                return {"ok": False, "reason": "Degenerate fit: all times identical"}
            beta_hat = denom / (n * sxy - sx * sy)
            intercept = (sy - beta_hat * sx) / n

        if beta_hat <= 0:
            return {"ok": False, "reason": f"Fit returned non-positive beta={beta_hat:.4g}"}

        eta_hat = math.exp(-intercept / beta_hat)

        # R² on Y vs X
        y_mean = sy / n
        ss_tot = sum((yi - y_mean) ** 2 for yi in fail_ys)
        y_pred = [beta_hat * xi + intercept for xi in fail_xs]
        ss_res = sum((yi - yp) ** 2 for yi, yp in zip(fail_ys, y_pred))
        r_sq = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

        if r_sq < 0.9:
            _warn_and_collect(
                f"weibull_fit: low R²={r_sq:.3f} — data may not follow Weibull", warns
            )

        return {
            "ok": True,
            "beta": beta_hat,
            "eta": eta_hat,
            "gamma": gamma,
            "r_squared": r_sq,
            "warnings": warns,
        }

    else:  # MLE
        # MLE for 2-parameter Weibull (no censoring in closed form; Newton-Raphson)
        # With censoring: combined failure + suspension times
        all_ts = [(t - gamma) for t in fail_times] + [(t - gamma) for t in susp_times]
        is_fail_flag = [True] * n_f + [False] * len(susp_times)
        n_tot = len(all_ts)

        # Initial guess from linear regression result
        beta_g = 1.5
        for _ in range(200):
            sum_tb = sum(t ** beta_g for t in all_ts)
            sum_tb_ln = sum(t ** beta_g * math.log(t) for t in all_ts)
            sum_ln_f = sum(math.log(t) for t, f in zip(all_ts, is_fail_flag) if f)

            # Score for beta
            score = n_f / beta_g + sum_ln_f - n_f * sum_tb_ln / sum_tb
            # Hessian diagonal
            sum_tb_ln2 = sum(t ** beta_g * (math.log(t) ** 2) for t in all_ts)
            hess = -n_f / beta_g ** 2 - n_f * (sum_tb * sum_tb_ln2 - sum_tb_ln ** 2) / sum_tb ** 2
            if abs(hess) < 1e-30:
                break
            step = score / (-hess)
            beta_g = beta_g + step
            if abs(step) < 1e-9:
                break
            if beta_g <= 0:
                beta_g = 0.01

        beta_hat = beta_g
        eta_hat = (sum_tb / n_f) ** (1.0 / beta_hat)

        if beta_hat <= 0 or not math.isfinite(beta_hat):
            return {"ok": False, "reason": "MLE did not converge to a valid beta"}

        return {
            "ok": True,
            "beta": beta_hat,
            "eta": eta_hat,
            "gamma": gamma,
            "r_squared": None,
            "warnings": warns,
        }


# ===========================================================================
# Exponential distribution
# ===========================================================================

def exponential_reliability(t: float, mtbf: float) -> dict:
    """
    Exponential reliability.

    R(t) = exp(-t / mtbf)  = exp(-lambda * t)

    Returns
    -------
    {"ok": True, "R": float, "F": float, "lambda": float, "warnings": [...]}
    """
    warns: list[str] = []
    if err := _guard_positive("mtbf", mtbf):
        return {"ok": False, "reason": err}
    if err := _guard_nonneg("t", t):
        return {"ok": False, "reason": err}
    lam = 1.0 / float(mtbf)
    R = math.exp(-float(t) * lam)
    if R < 0.1:
        _warn_and_collect(f"exponential_reliability: low R={R:.4f} at t={t}", warns)
    return {"ok": True, "R": R, "F": 1.0 - R, "lambda": lam, "warnings": warns}


def exponential_mtbf_ci(
    failures: int,
    test_time: float,
    *,
    confidence: float = 0.9,
) -> dict:
    """
    Chi-square confidence interval on MTBF from test data (MIL-HDBK-189).

    Assumption: failures follow a homogeneous Poisson process (HPP).

    MTBF_lower = 2*T / chi2(1 - alpha/2, 2*r+2)
    MTBF_upper = 2*T / chi2(alpha/2, 2*r)

    For failures = 0 (time-terminated test), only a lower bound is given.

    Parameters
    ----------
    failures   : number of observed failures (>= 0)
    test_time  : total accumulated test time (> 0)
    confidence : two-sided confidence level (default 0.90)

    Returns
    -------
    {"ok": True, "mtbf_point": float, "mtbf_lower": float, "mtbf_upper": float,
     "confidence": float, "warnings": [...]}
    """
    warns: list[str] = []
    if not isinstance(failures, int) or failures < 0:
        return {"ok": False, "reason": f"failures must be a non-negative integer, got {failures!r}"}
    if err := _guard_positive("test_time", test_time):
        return {"ok": False, "reason": err}
    if not (0.0 < confidence < 1.0):
        return {"ok": False, "reason": f"confidence must be in (0,1), got {confidence}"}

    T = float(test_time)
    r = failures
    alpha = 1.0 - confidence

    # Point estimate
    if r == 0:
        mtbf_point = float("inf")
        _warn_and_collect(
            "exponential_mtbf_ci: 0 failures — point estimate is inf; "
            "only lower bound is meaningful",
            warns,
        )
    else:
        mtbf_point = T / r

    # Lower bound: chi2(1 - alpha/2, df=2*(r+1))
    df_lower = 2 * (r + 1)
    chi2_upper = _chi2_ppf(1.0 - alpha / 2.0, df_lower)
    mtbf_lower = 2.0 * T / chi2_upper

    # Upper bound: chi2(alpha/2, df=2*r)  — only defined when r > 0
    if r > 0:
        df_upper = 2 * r
        chi2_lower = _chi2_ppf(alpha / 2.0, df_upper)
        mtbf_upper = 2.0 * T / chi2_lower if chi2_lower > 1e-30 else float("inf")
    else:
        mtbf_upper = float("inf")

    if mtbf_lower < 0.1 * test_time:
        _warn_and_collect(
            f"exponential_mtbf_ci: narrow lower bound (MTBF_lower/T = "
            f"{mtbf_lower/test_time:.3f}) — consider more test time",
            warns,
        )

    return {
        "ok": True,
        "mtbf_point": mtbf_point,
        "mtbf_lower": mtbf_lower,
        "mtbf_upper": mtbf_upper,
        "confidence": confidence,
        "warnings": warns,
    }


# ===========================================================================
# System reliability
# ===========================================================================

def system_series(reliabilities: list) -> dict:
    """
    Series system reliability: all components must work.

    R_s = product(R_i)

    Returns
    -------
    {"ok": True, "R_system": float, "n": int, "warnings": [...]}
    """
    warns: list[str] = []
    if not reliabilities:
        return {"ok": False, "reason": "reliabilities must be a non-empty list"}
    R_s = 1.0
    for i, r in enumerate(reliabilities):
        if err := _guard_prob(f"reliabilities[{i}]", r):
            return {"ok": False, "reason": err}
        R_s *= float(r)
    if R_s < 0.5:
        _warn_and_collect(
            f"system_series: system reliability R={R_s:.4f} is below 0.5", warns
        )
    return {"ok": True, "R_system": R_s, "n": len(reliabilities), "warnings": warns}


def system_parallel(reliabilities: list) -> dict:
    """
    Active parallel system: at least one component must work.

    R_s = 1 - product(1 - R_i)

    Returns
    -------
    {"ok": True, "R_system": float, "n": int, "warnings": [...]}
    """
    warns: list[str] = []
    if not reliabilities:
        return {"ok": False, "reason": "reliabilities must be a non-empty list"}
    Q_s = 1.0
    for i, r in enumerate(reliabilities):
        if err := _guard_prob(f"reliabilities[{i}]", r):
            return {"ok": False, "reason": err}
        Q_s *= 1.0 - float(r)
    R_s = 1.0 - Q_s
    if R_s < 0.5:
        _warn_and_collect(
            f"system_parallel: system reliability R={R_s:.4f} is below 0.5", warns
        )
    return {"ok": True, "R_system": R_s, "n": len(reliabilities), "warnings": warns}


def system_k_out_of_n(k: int, n: int, r: float) -> dict:
    """
    k-out-of-n system reliability (all components identical).

    R = sum_{i=k}^{n} C(n,i) * r^i * (1-r)^(n-i)

    The system succeeds if at least k of n components work.

    Returns
    -------
    {"ok": True, "R_system": float, "k": int, "n": int, "warnings": [...]}
    """
    warns: list[str] = []
    if not isinstance(k, int) or k < 1:
        return {"ok": False, "reason": f"k must be a positive integer, got {k!r}"}
    if not isinstance(n, int) or n < 1:
        return {"ok": False, "reason": f"n must be a positive integer, got {n!r}"}
    if k > n:
        return {"ok": False, "reason": f"k ({k}) must be <= n ({n})"}
    if err := _guard_prob("r", r):
        return {"ok": False, "reason": err}

    r = float(r)
    q = 1.0 - r
    R_s = sum(_comb(n, i) * r**i * q**(n - i) for i in range(k, n + 1))
    R_s = max(0.0, min(1.0, R_s))  # clamp floating-point noise
    if R_s < 0.5:
        _warn_and_collect(
            f"system_k_out_of_n: system reliability R={R_s:.4f} is below 0.5", warns
        )
    return {"ok": True, "R_system": R_s, "k": k, "n": n, "warnings": warns}


def system_bridge(r_list: list) -> dict:
    """
    5-component bridge reliability via total probability decomposition.

    Standard bridge topology:
      Component 3 is the "bridge" component connecting middle nodes.
      Decompose on component 3: condition on it working/failed.

      Nodes: A—[1]—B—[5]—D
             A—[2]—C—[4]—D
                B—[3]—C

    Labelling follows O'Connor §4.3 bridge network (components 1–5).
    r_list must have exactly 5 elements [r1, r2, r3, r4, r5].

    Returns
    -------
    {"ok": True, "R_system": float, "warnings": [...]}
    """
    warns: list[str] = []
    if len(r_list) != 5:
        return {"ok": False, "reason": f"r_list must have exactly 5 elements, got {len(r_list)}"}
    rs = []
    for i, r in enumerate(r_list):
        if err := _guard_prob(f"r_list[{i}]", r):
            return {"ok": False, "reason": err}
        rs.append(float(r))

    r1, r2, r3, r4, r5 = rs
    # When bridge component 3 works (prob r3):
    #   Top path: series(1,5) || series(2,4) → but nodes are now linked
    #   System becomes: [1||2] in series with [4||5]
    #   Actually with bridge working: (1+2-1*2)*(4+5-4*5)
    top_r3_works = (r1 + r2 - r1 * r2) * (r4 + r5 - r4 * r5)
    # When bridge component 3 fails (prob 1-r3):
    #   Two independent paths: 1-5 and 2-4 in parallel
    top_r3_fails = (r1 * r5) + (r2 * r4) - (r1 * r5 * r2 * r4)

    R_s = r3 * top_r3_works + (1.0 - r3) * top_r3_fails

    if R_s < 0.5:
        _warn_and_collect(
            f"system_bridge: system reliability R={R_s:.4f} is below 0.5", warns
        )
    return {"ok": True, "R_system": R_s, "warnings": warns}


def availability(mtbf: float, mttr: float) -> dict:
    """
    Steady-state availability (inherent).

    A = MTBF / (MTBF + MTTR)

    Parameters
    ----------
    mtbf : mean time between failures (> 0)
    mttr : mean time to repair (> 0)

    Returns
    -------
    {"ok": True, "availability": float, "unavailability": float, "warnings": [...]}
    """
    warns: list[str] = []
    if err := _guard_positive("mtbf", mtbf):
        return {"ok": False, "reason": err}
    if err := _guard_positive("mttr", mttr):
        return {"ok": False, "reason": err}

    A = float(mtbf) / (float(mtbf) + float(mttr))
    if A < 0.9:
        _warn_and_collect(
            f"availability: low availability A={A:.4f} — consider reducing MTTR or "
            "increasing MTBF",
            warns,
        )
    return {
        "ok": True,
        "availability": A,
        "unavailability": 1.0 - A,
        "warnings": warns,
    }


def redundancy_gain(r: float, n_active: int, *, n_standby: int = 0) -> dict:
    """
    Reliability gain from redundancy (active or standby).

    Active parallel (n_active components in parallel, no standby):
      R_active = 1 - (1 - r)^n_active

    Perfect standby (n_standby additional units switched in on failure,
    exponential failure model assumed, i.e. Poisson process):
      R_standby = R_active * sum_{i=0}^{n_standby} (lambda*t)^i / i! * exp(-lambda*t)
      … but without absolute time, we return the ratio gain factor.

    For practical purposes this function returns:
      - R_active    : pure active-parallel result
      - R_with_standby : approximate improvement if n_standby spares available
        (using the parallel formula for combined n_active + n_standby out of
        n_active + n_standby, which is an upper bound on standby benefit).
      - gain_active : R_active / r
      - gain_standby: R_with_standby / r (if n_standby > 0)

    Returns
    -------
    {"ok": True, "R_active": float, "gain_active": float,
     "R_with_standby": float, "gain_standby": float, "warnings": [...]}
    """
    warns: list[str] = []
    if err := _guard_prob("r", r):
        return {"ok": False, "reason": err}
    if not isinstance(n_active, int) or n_active < 1:
        return {"ok": False, "reason": f"n_active must be a positive integer, got {n_active!r}"}
    if not isinstance(n_standby, int) or n_standby < 0:
        return {"ok": False, "reason": f"n_standby must be a non-negative integer, got {n_standby!r}"}

    r = float(r)
    R_active = 1.0 - (1.0 - r) ** n_active
    gain_active = R_active / r if r > 0 else float("inf")

    n_total = n_active + n_standby
    R_standby = 1.0 - (1.0 - r) ** n_total
    gain_standby = R_standby / r if r > 0 else float("inf")

    if R_active < 0.9:
        _warn_and_collect(
            f"redundancy_gain: active R={R_active:.4f} still below 0.9 — "
            "consider more parallel units",
            warns,
        )
    return {
        "ok": True,
        "R_active": R_active,
        "gain_active": gain_active,
        "R_with_standby": R_standby,
        "gain_standby": gain_standby,
        "warnings": warns,
    }


# ===========================================================================
# Stress-strength interference
# ===========================================================================

def stress_strength_normal(
    mu_s: float,
    sigma_s: float,
    mu_r: float,
    sigma_r: float,
) -> dict:
    """
    Closed-form stress-strength reliability for normal distributions.

    R = P(strength > stress) = Phi(z)
    z = (mu_r - mu_s) / sqrt(sigma_r^2 + sigma_s^2)

    Parameters
    ----------
    mu_s    : mean stress
    sigma_s : std dev of stress (> 0)
    mu_r    : mean strength (resistance)
    sigma_r : std dev of strength (> 0)

    Returns
    -------
    {"ok": True, "R": float, "z": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("sigma_s", sigma_s), ("sigma_r", sigma_r)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}
    for name, val in (("mu_s", mu_s), ("mu_r", mu_r)):
        try:
            float(val)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"{name} must be a number"}

    sigma_s = float(sigma_s)
    sigma_r = float(sigma_r)
    mu_s = float(mu_s)
    mu_r = float(mu_r)

    z = (mu_r - mu_s) / math.sqrt(sigma_r**2 + sigma_s**2)
    R = _norm_cdf(z)

    if R < 0.9:
        _warn_and_collect(
            f"stress_strength_normal: low reliability R={R:.4f} (z={z:.2f}) — "
            "increase margin or reduce variability",
            warns,
        )
    return {"ok": True, "R": R, "z": z, "warnings": warns}


def stress_strength_numeric(
    stress_samples: list,
    strength_samples: list,
) -> dict:
    """
    Empirical / Monte-Carlo stress-strength reliability.

    R ≈ count(strength > stress) / n_pairs

    If the two lists have different lengths, the shorter is replicated via
    round-robin to match the longer.

    Returns
    -------
    {"ok": True, "R": float, "n_pairs": int, "warnings": [...]}
    """
    warns: list[str] = []
    if not stress_samples:
        return {"ok": False, "reason": "stress_samples must be a non-empty list"}
    if not strength_samples:
        return {"ok": False, "reason": "strength_samples must be a non-empty list"}

    try:
        ss = [float(v) for v in stress_samples]
        sr = [float(v) for v in strength_samples]
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"non-numeric value: {exc}"}

    n = max(len(ss), len(sr))
    ss_ext = [ss[i % len(ss)] for i in range(n)]
    sr_ext = [sr[i % len(sr)] for i in range(n)]

    n_ok = sum(1 for s, r in zip(ss_ext, sr_ext) if r > s)
    R = n_ok / n

    if len(ss) < 30 or len(sr) < 30:
        _warn_and_collect(
            "stress_strength_numeric: fewer than 30 samples — empirical R may be "
            "inaccurate",
            warns,
        )
    if R < 0.9:
        _warn_and_collect(
            f"stress_strength_numeric: low reliability R={R:.4f}", warns
        )
    return {"ok": True, "R": R, "n_pairs": n, "warnings": warns}


# ===========================================================================
# FMEA
# ===========================================================================

def fmea_rpn(severity: int, occurrence: int, detection: int) -> dict:
    """
    FMEA Risk Priority Number.

    RPN = S × O × D,  each rating in 1–10.

    Severity   (S): effect on customer (1=minor, 10=hazardous without warning)
    Occurrence (O): likelihood of failure (1=unlikely, 10=very high)
    Detection  (D): ability to detect before reaching customer (1=certain, 10=no way)

    RPN >= 100 is generally considered high risk.

    Returns
    -------
    {"ok": True, "RPN": int, "severity": int, "occurrence": int,
     "detection": int, "risk_level": str, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("severity", severity), ("occurrence", occurrence), ("detection", detection)):
        if not isinstance(val, int) or not (1 <= val <= 10):
            return {"ok": False, "reason": f"{name} must be an integer in [1, 10], got {val!r}"}

    rpn = severity * occurrence * detection
    if rpn >= 200:
        risk = "critical"
        _warn_and_collect(f"fmea_rpn: RPN={rpn} is CRITICAL (>= 200) — immediate action required", warns)
    elif rpn >= 100:
        risk = "high"
        _warn_and_collect(f"fmea_rpn: RPN={rpn} is HIGH (>= 100) — action recommended", warns)
    elif rpn >= 50:
        risk = "medium"
    else:
        risk = "low"

    return {
        "ok": True,
        "RPN": rpn,
        "severity": severity,
        "occurrence": occurrence,
        "detection": detection,
        "risk_level": risk,
        "warnings": warns,
    }


def fmea_criticality(
    severity: float,
    occurrence: float,
    *,
    mode_ratio: float = 1.0,
) -> dict:
    """
    FMEA criticality number (MIL-STD-1629A method).

    Cm = beta_m × alpha_t × occurrence_rate × exposure_time

    In simplified form (when only severity and occurrence are known):
      Criticality = mode_ratio × severity × occurrence

    Parameters
    ----------
    severity    : severity category (1–10 or categorical weight)
    occurrence  : failure rate or occurrence probability (> 0)
    mode_ratio  : fraction of failures due to this mode (0 < mode_ratio <= 1,
                  default 1.0)

    Returns
    -------
    {"ok": True, "criticality": float, "warnings": [...]}
    """
    warns: list[str] = []
    try:
        sev = float(severity)
        occ = float(occurrence)
        mr = float(mode_ratio)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"non-numeric input: {exc}"}

    if sev <= 0:
        return {"ok": False, "reason": f"severity must be > 0, got {sev}"}
    if occ <= 0:
        return {"ok": False, "reason": f"occurrence must be > 0, got {occ}"}
    if not (0 < mr <= 1.0):
        return {"ok": False, "reason": f"mode_ratio must be in (0, 1], got {mr}"}

    criticality = mr * sev * occ
    if criticality > 50:
        _warn_and_collect(
            f"fmea_criticality: high criticality={criticality:.2f} — "
            "prioritise mitigation",
            warns,
        )
    return {"ok": True, "criticality": criticality, "warnings": warns}


# ===========================================================================
# Fault tree analysis
# ===========================================================================

def _eval_tree(node: dict) -> float:
    """
    Recursively evaluate the probability of the top event for a fault-tree node.

    Node format:
      {"type": "basic", "id": "E1", "p": 0.01}
      {"type": "AND",   "children": [...]}
      {"type": "OR",    "children": [...]}
      {"type": "K_OF_N", "k": 2, "n": 3, "p": 0.01}
    """
    node_type = node.get("type", "").upper()
    if node_type == "BASIC":
        return float(node["p"])
    elif node_type == "AND":
        p = 1.0
        for child in node.get("children", []):
            p *= _eval_tree(child)
        return p
    elif node_type == "OR":
        q = 1.0
        for child in node.get("children", []):
            q *= 1.0 - _eval_tree(child)
        return 1.0 - q
    elif node_type == "K_OF_N":
        k = int(node["k"])
        n = int(node.get("n", len(node.get("children", []))))
        p_child = float(node["p"])
        return sum(_comb(n, i) * p_child**i * (1 - p_child)**(n - i) for i in range(k, n + 1))
    else:
        raise ValueError(f"Unknown fault-tree node type: {node_type!r}")


def fault_tree_top(tree: dict) -> dict:
    """
    Evaluate the top-event probability of a fault tree.

    Parameters
    ----------
    tree : nested dict describing the fault tree.
      Basic event: {"type": "basic", "id": "<name>", "p": <float>}
      AND gate:    {"type": "AND", "children": [<node>, ...]}
      OR gate:     {"type": "OR",  "children": [<node>, ...]}
      k-of-n gate: {"type": "K_OF_N", "k": <int>, "n": <int>, "p": <float>}

    Returns
    -------
    {"ok": True, "p_top": float, "warnings": [...]}
    """
    warns: list[str] = []
    if not isinstance(tree, dict):
        return {"ok": False, "reason": "tree must be a dict"}
    try:
        p = _eval_tree(tree)
    except Exception as exc:
        return {"ok": False, "reason": f"fault tree evaluation error: {exc}"}

    if p > 0.01:
        _warn_and_collect(
            f"fault_tree_top: top-event probability p={p:.4g} > 0.01 — "
            "consider design changes",
            warns,
        )
    return {"ok": True, "p_top": p, "warnings": warns}


def _collect_basics(node: dict) -> list[str]:
    """Return list of all basic event IDs in the tree."""
    t = node.get("type", "").upper()
    if t == "BASIC":
        return [node["id"]]
    ids: list[str] = []
    for child in node.get("children", []):
        ids.extend(_collect_basics(child))
    return ids


def _minimal_cut_sets(node: dict) -> list[frozenset]:
    """
    Boolean-algebra minimal cut sets (MCS) via recursive expansion.

    Rules:
      AND gate  → cartesian product of children MCS
      OR gate   → union of children MCS
      BASIC     → singleton set

    Returns list of frozensets (each = one MCS).
    """
    t = node.get("type", "").upper()
    if t == "BASIC":
        return [frozenset([node["id"]])]
    elif t == "OR":
        sets: list[frozenset] = []
        for child in node.get("children", []):
            sets.extend(_minimal_cut_sets(child))
        # Remove non-minimal: a set A is non-minimal if some B in sets where B ⊂ A
        minimal: list[frozenset] = []
        for s in sets:
            if not any(other < s for other in sets if other is not s):
                minimal.append(s)
        return minimal
    elif t == "AND":
        children_mcs = [_minimal_cut_sets(c) for c in node.get("children", [])]
        # Cartesian product
        result = [frozenset()]
        for mcs_list in children_mcs:
            new_result = []
            for existing in result:
                for mcs in mcs_list:
                    new_result.append(existing | mcs)
            result = new_result
        # Absorb non-minimals
        minimal = []
        for s in result:
            if not any(other < s for other in result if other is not s):
                minimal.append(s)
        return minimal
    elif t == "K_OF_N":
        # Treat k-of-n as OR of all k-combinations of children events
        k = int(node["k"])
        n = int(node.get("n", 1))
        event_id = node.get("id", "E_?")
        # Represent as singleton (simplified: treat k-of-n as a single event)
        return [frozenset([f"{event_id}_{i}" for i in range(k)])]
    else:
        return []


def fault_tree_cut_sets(tree: dict) -> dict:
    """
    Enumerate minimal cut sets from a fault tree.

    Returns
    -------
    {"ok": True, "cut_sets": [[str, ...], ...], "n_cut_sets": int, "warnings": [...]}
    """
    warns: list[str] = []
    if not isinstance(tree, dict):
        return {"ok": False, "reason": "tree must be a dict"}
    try:
        mcs = _minimal_cut_sets(tree)
    except Exception as exc:
        return {"ok": False, "reason": f"cut-set computation error: {exc}"}

    cut_sets = [sorted(s) for s in mcs]
    if len(cut_sets) > 50:
        _warn_and_collect(
            f"fault_tree_cut_sets: {len(cut_sets)} cut sets — very complex tree", warns
        )
    return {
        "ok": True,
        "cut_sets": cut_sets,
        "n_cut_sets": len(cut_sets),
        "warnings": warns,
    }


def fault_tree_importance(tree: dict, event_id: str) -> dict:
    """
    Birnbaum structural importance of a basic event.

    I_B(i) = P(system fails | event i occurs) - P(system fails | event i does not occur)

    Computed numerically by evaluating the tree with p_i=1 and p_i=0.

    Parameters
    ----------
    tree     : fault tree dict (same format as fault_tree_top)
    event_id : ID of the basic event to compute importance for

    Returns
    -------
    {"ok": True, "I_birnbaum": float, "event_id": str, "warnings": [...]}
    """
    warns: list[str] = []
    if not isinstance(tree, dict):
        return {"ok": False, "reason": "tree must be a dict"}

    import copy

    def _set_p(node: dict, eid: str, val: float) -> dict:
        n = copy.deepcopy(node)
        if n.get("type", "").upper() == "BASIC" and n.get("id") == eid:
            n["p"] = val
            return n
        if "children" in n:
            n["children"] = [_set_p(c, eid, val) for c in n["children"]]
        return n

    try:
        tree_1 = _set_p(tree, event_id, 1.0)
        tree_0 = _set_p(tree, event_id, 0.0)
        p1 = _eval_tree(tree_1)
        p0 = _eval_tree(tree_0)
    except Exception as exc:
        return {"ok": False, "reason": f"importance computation error: {exc}"}

    importance = p1 - p0
    if importance == 0:
        _warn_and_collect(
            f"fault_tree_importance: event '{event_id}' has zero Birnbaum importance — "
            "it may not be connected to the top event",
            warns,
        )
    return {
        "ok": True,
        "I_birnbaum": importance,
        "event_id": event_id,
        "warnings": warns,
    }


# ===========================================================================
# Reliability allocation
# ===========================================================================

def reliability_allocation_equal(r_system: float, n_components: int) -> dict:
    """
    Equal (uniform) reliability apportionment.

    Each component is assigned the same reliability:
      r_i = r_sys^(1/n)

    (Assumes series system.)

    Returns
    -------
    {"ok": True, "r_component": float, "r_system": float,
     "n_components": int, "warnings": [...]}
    """
    warns: list[str] = []
    if err := _guard_prob("r_system", r_system):
        return {"ok": False, "reason": err}
    if not isinstance(n_components, int) or n_components < 1:
        return {"ok": False, "reason": f"n_components must be a positive integer, got {n_components!r}"}

    if float(r_system) == 0.0:
        return {"ok": False, "reason": "r_system=0 — no allocation possible"}

    r_i = float(r_system) ** (1.0 / n_components)
    return {
        "ok": True,
        "r_component": r_i,
        "r_system": r_system,
        "n_components": n_components,
        "warnings": warns,
    }


def reliability_allocation_agree(
    r_system: float,
    importances: list,
    *,
    n_i: list | None = None,
    t_i: list | None = None,
    lambda_g: float = 1.0,
) -> dict:
    """
    AGREE (Advisory Group on Reliability of Electronic Equipment) allocation.

    Each subsystem i is allocated:
      r_i = exp(-n_i * t_i * (-ln(r_sys)) / (importance_i * N * t_mission))

    Simplified form when n_i, t_i are equal (each subsystem has n_i modules
    operating for t_i hours):
      lambda_i = importance_i * lambda_sys / n_i

    Parameters
    ----------
    r_system    : required system reliability (series assumption)
    importances : list of subsystem importance weights (sum normalised to 1 internally)
    n_i         : list of number of modules per subsystem (default: all 1)
    t_i         : list of operating times per subsystem (default: all equal to 1)
    lambda_g    : system-level failure rate scale (default 1.0; unused if >0)

    Returns
    -------
    {"ok": True, "allocations": [{"subsystem": i, "r_i": float, "lambda_i": float}],
     "r_system": float, "warnings": [...]}
    """
    warns: list[str] = []
    if err := _guard_prob("r_system", r_system):
        return {"ok": False, "reason": err}
    if not importances:
        return {"ok": False, "reason": "importances must be a non-empty list"}

    n_sub = len(importances)
    try:
        imps = [float(w) for w in importances]
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"non-numeric importance: {exc}"}
    if any(w <= 0 for w in imps):
        return {"ok": False, "reason": "all importances must be > 0"}

    # Normalise importances
    total_imp = sum(imps)
    imps_norm = [w / total_imp for w in imps]

    n_vals = [1] * n_sub if n_i is None else list(n_i)
    t_vals = [1.0] * n_sub if t_i is None else [float(v) for v in t_i]

    if len(n_vals) != n_sub:
        return {"ok": False, "reason": f"n_i length ({len(n_vals)}) != importances length ({n_sub})"}
    if len(t_vals) != n_sub:
        return {"ok": False, "reason": f"t_i length ({len(t_vals)}) != importances length ({n_sub})"}

    r_sys = float(r_system)
    lambda_sys = -math.log(r_sys) if r_sys > 0 else float("inf")

    allocations = []
    for i in range(n_sub):
        n_sub_i = float(n_vals[i])
        t_sub_i = float(t_vals[i])
        if n_sub_i <= 0:
            return {"ok": False, "reason": f"n_i[{i}] must be > 0"}
        if t_sub_i <= 0:
            return {"ok": False, "reason": f"t_i[{i}] must be > 0"}

        # Allocate failure rate proportional to importance
        lambda_i = imps_norm[i] * lambda_sys / n_sub_i
        r_i = math.exp(-lambda_i * t_sub_i)
        allocations.append({
            "subsystem": i,
            "importance": imps_norm[i],
            "lambda_i": lambda_i,
            "r_i": r_i,
        })

    # Verify product
    r_achieved = math.exp(-sum(a["lambda_i"] * t_vals[i] for i, a in enumerate(allocations)))
    if abs(r_achieved - r_sys) > 1e-6:
        _warn_and_collect(
            f"reliability_allocation_agree: achieved R={r_achieved:.6f} differs from "
            f"target R={r_sys:.6f}",
            warns,
        )

    return {
        "ok": True,
        "allocations": allocations,
        "r_system": r_system,
        "warnings": warns,
    }


# ===========================================================================
# Accelerated life testing
# ===========================================================================

def arrhenius_af(E_a: float, T_use_K: float, T_acc_K: float) -> dict:
    """
    Arrhenius temperature acceleration factor.

    AF = exp(E_a / k * (1/T_use - 1/T_acc))

    where k = 8.617e-5 eV/K (Boltzmann constant).

    Parameters
    ----------
    E_a    : activation energy (eV).  Typical range: 0.3–1.2 eV.
    T_use_K: use/field temperature (Kelvin, > 0)
    T_acc_K: accelerated test temperature (Kelvin, > T_use_K recommended)

    Returns
    -------
    {"ok": True, "AF": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("E_a", E_a), ("T_use_K", T_use_K), ("T_acc_K", T_acc_K)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}

    E_a = float(E_a)
    T_use = float(T_use_K)
    T_acc = float(T_acc_K)

    if T_acc <= T_use:
        _warn_and_collect(
            f"arrhenius_af: T_acc ({T_acc} K) <= T_use ({T_use} K) — AF will be < 1, "
            "i.e. deceleration",
            warns,
        )

    AF = math.exp(E_a / _K_BOLTZMANN_EV * (1.0 / T_use - 1.0 / T_acc))
    if AF < 1.0:
        _warn_and_collect(
            f"arrhenius_af: AF={AF:.4f} < 1 — accelerated stress is weaker than use stress",
            warns,
        )
    return {"ok": True, "AF": AF, "E_a_eV": E_a, "T_use_K": T_use, "T_acc_K": T_acc,
            "warnings": warns}


def inverse_power_af(V_use: float, V_acc: float, n: float) -> dict:
    """
    Inverse power law acceleration factor (for non-thermal stresses).

    AF = (V_acc / V_use)^n

    Common stresses: voltage (n≈3–5 for dielectrics), vibration, humidity.

    Parameters
    ----------
    V_use : use-condition stress level (> 0)
    V_acc : accelerated-test stress level (> 0)
    n     : life-stress exponent (> 0)

    Returns
    -------
    {"ok": True, "AF": float, "warnings": [...]}
    """
    warns: list[str] = []
    for name, val in (("V_use", V_use), ("V_acc", V_acc), ("n", n)):
        if err := _guard_positive(name, val):
            return {"ok": False, "reason": err}

    V_use = float(V_use)
    V_acc = float(V_acc)
    n = float(n)

    if V_acc <= V_use:
        _warn_and_collect(
            f"inverse_power_af: V_acc ({V_acc}) <= V_use ({V_use}) — AF < 1 (deceleration)",
            warns,
        )

    AF = (V_acc / V_use) ** n
    if AF < 1.0:
        _warn_and_collect(
            f"inverse_power_af: AF={AF:.4f} < 1 — test stress is below use stress",
            warns,
        )
    return {"ok": True, "AF": AF, "V_use": V_use, "V_acc": V_acc, "n": n, "warnings": warns}
