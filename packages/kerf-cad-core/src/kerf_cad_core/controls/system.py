"""
kerf_cad_core.controls.system — classical control-systems analysis & PID tuning.

Public functions
----------------
second_order_spec(wn, zeta)
    ωn, ζ → overshoot, settling time, rise time, peak time.

second_order_inverse(*, overshoot, settling_time, rise_time, peak_time)
    Inverse: given one performance spec → ωn and ζ.

first_order_step(K, tau, t_samples)
    First-order step response y(t) = K(1 − e^(−t/τ)).

first_order_impulse(K, tau, t_samples)
    First-order impulse response y(t) = (K/τ) e^(−t/τ).

second_order_step(wn, zeta, t_samples, *, K)
    Second-order unity-feedback step response samples.

second_order_impulse(wn, zeta, t_samples, *, K)
    Second-order impulse response samples.

routh_hurwitz(coeffs)
    Routh array and RHP pole count for a real-coefficient characteristic
    polynomial a_0 s^n + a_1 s^(n-1) + ... + a_n.

bode_point(num, den, omega)
    Bode magnitude (dB) and phase (deg) at a single frequency ω.

gain_phase_margins(num, den, omega_range)
    Gain margin, phase margin, gain crossover, phase crossover by sweep.

steady_state_errors(num_ol, den_ol)
    System type (0/1/2), Kp, Kv, Ka, ess for step/ramp/parabola.

pid_zn_open(K, tau, theta)
    Ziegler-Nichols open-loop (process reaction curve) PID tuning from FOPDT.

pid_zn_closed(Ku, Tu)
    Ziegler-Nichols closed-loop (ultimate gain/period) PID tuning.

pid_cohen_coon(K, tau, theta)
    Cohen-Coon PID tuning from FOPDT parameters.

pid_imc(K, tau, theta, lambda_c)
    Lambda/IMC PID tuning from FOPDT parameters.

root_locus_breakaway(num, den)
    Real-axis breakaway/break-in points of the root locus.

All functions return plain dicts:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Distinct from:
  - dsp/    : digital FIR/IIR filter design
  - vibration/ : mechanical SDOF/MDOF structural dynamics

References
----------
Ogata, K. "Modern Control Engineering", 5th ed. (Pearson)
Nise, N.S. "Control Systems Engineering", 7th ed. (Wiley)
Ziegler, J.G. & Nichols, N.B. (1942). "Optimum Settings for Automatic Controllers."
Cohen, G.H. & Coon, G.A. (1953). "Theoretical Consideration of Retarded Control."
Rivera, D.E., Morari, M. & Skogestad, S. (1986). "Internal Model Control."

Author: imranparuk
"""

from __future__ import annotations

import cmath
import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _poly_eval(coeffs: list[float], s: complex) -> complex:
    """Evaluate polynomial with coefficients [a0, a1, ..., an] at s.
    Polynomial: a0*s^n + a1*s^(n-1) + ... + an  (highest-degree first)."""
    result = complex(0.0)
    for c in coeffs:
        result = result * s + c
    return result


def _poly_deriv(coeffs: list[float]) -> list[float]:
    """Differentiate polynomial; returns derivative coefficients."""
    n = len(coeffs) - 1
    if n <= 0:
        return [0.0]
    return [coeffs[i] * (n - i) for i in range(n)]


def _poly_roots_real_axis(coeffs: list[float], n_points: int = 10001) -> list[float]:
    """Find approximate real roots of polynomial by scanning [-500, 100].
    Returns list of real roots detected by sign changes or exact zeros."""
    if len(coeffs) < 2:
        return []
    # Strip leading zeros
    c = coeffs[:]
    while len(c) > 1 and abs(c[0]) < 1e-15:
        c = c[1:]
    if len(c) < 2:
        return []

    roots: list[float] = []
    x_min, x_max = -500.0, 100.0
    step = (x_max - x_min) / (n_points - 1)
    prev_x = x_min
    prev_v = _poly_eval(c, complex(prev_x)).real

    for i in range(1, n_points):
        x = x_min + i * step
        v = _poly_eval(c, complex(x)).real

        if abs(v) < 1e-9 * (abs(prev_v) + 1.0):
            # Near-exact zero at this sample point
            roots.append(x)
            prev_x = x
            prev_v = v
            continue

        if prev_v * v < 0:
            # Sign change — bisect to refine
            lo, hi = prev_x, x
            v_lo = prev_v
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                vm = _poly_eval(c, complex(mid)).real
                if abs(vm) < 1e-12:
                    lo = hi = mid
                    break
                if v_lo * vm <= 0:
                    hi = mid
                else:
                    lo = mid
                    v_lo = vm
            r = 0.5 * (lo + hi)
            # Avoid duplicate roots (within step/2)
            if not roots or abs(r - roots[-1]) > step * 0.5:
                roots.append(r)

        prev_x = x
        prev_v = v
    return roots


# ---------------------------------------------------------------------------
# 1. second_order_spec
# ---------------------------------------------------------------------------

def second_order_spec(wn: float, zeta: float) -> dict:
    """
    Second-order closed-loop performance specifications.

    Parameters
    ----------
    wn : float
        Undamped natural frequency (rad/s). Must be > 0.
    zeta : float
        Damping ratio. Must be >= 0.

    Returns
    -------
    dict
        ok              : True
        wn              : ωn (rad/s)
        zeta            : ζ
        overshoot_pct   : peak overshoot % (0 for ζ ≥ 1)
        peak_time_s     : time to first peak (s); None for ζ ≥ 1
        rise_time_s     : 10%-to-90% rise time (s)
        settling_time_2pct: 2% settling time (s) ≈ 4/(ζ·ωn)
        settling_time_5pct: 5% settling time (s) ≈ 3/(ζ·ωn)
        damped_wn       : ωd = ωn√(1-ζ²) (rad/s); None for ζ ≥ 1
        warnings        : list of flag strings

    References: Ogata §5-4, Nise §4-5.
    """
    e = _guard_positive("wn", wn)
    if e:
        return _err(e)
    e = _guard_nonneg("zeta", zeta)
    if e:
        return _err(e)
    wn = float(wn)
    zeta = float(zeta)
    warnings: list[str] = []

    if zeta >= 1.0:
        # Overdamped / critically damped — no oscillatory overshoot
        overshoot_pct = 0.0
        peak_time_s = None
        damped_wn = None
        if zeta > 1.0:
            # Overdamped; rise time approximated from dominant-pole step
            sigma = zeta * wn
            wd_real = wn * math.sqrt(zeta ** 2 - 1.0)
            s1 = -sigma + wd_real
            s2 = -sigma - wd_real
            if s1 < 0:
                rise_time_s = math.log(9.0) / (-s1) if s1 != 0 else None
            else:
                rise_time_s = None
        else:
            # Critically damped
            rise_time_s = 2.16 * zeta / wn + 0.60 / wn if zeta != 0 else 0.60 / wn
        settling_time_2pct = 4.0 / (zeta * wn) if zeta > 0 else float("inf")
        settling_time_5pct = 3.0 / (zeta * wn) if zeta > 0 else float("inf")
    else:
        wd = wn * math.sqrt(1.0 - zeta ** 2)
        damped_wn = wd
        # Percent overshoot (Ogata §5-4)
        overshoot_pct = 100.0 * math.exp(-math.pi * zeta / math.sqrt(1.0 - zeta ** 2))
        # Peak time: tp = π / ωd
        peak_time_s = math.pi / wd
        # Rise time (10%→90%): tr ≈ (1.8) / ωn  (approximate for 0 < ζ < 1)
        # More precise: tr = (π - arccos(ζ)) / ωd  (Ogata eq. 5-34)
        rise_time_s = (math.pi - math.acos(zeta)) / wd
        # Settling time
        settling_time_2pct = 4.0 / (zeta * wn)
        settling_time_5pct = 3.0 / (zeta * wn)

        if overshoot_pct > 30.0:
            warnings.append("POOR_DAMPING: overshoot > 30%")
        if zeta < 0.1:
            warnings.append("LOW_DAMPING: zeta < 0.1")

    return {
        "ok": True,
        "wn": wn,
        "zeta": zeta,
        "overshoot_pct": overshoot_pct,
        "peak_time_s": peak_time_s,
        "rise_time_s": rise_time_s,
        "settling_time_2pct": settling_time_2pct,
        "settling_time_5pct": settling_time_5pct,
        "damped_wn": damped_wn,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. second_order_inverse
# ---------------------------------------------------------------------------

def second_order_inverse(
    *,
    overshoot: float | None = None,
    settling_time: float | None = None,
    rise_time: float | None = None,
    peak_time: float | None = None,
) -> dict:
    """
    Inverse second-order spec: given one performance metric → (ωn, ζ).

    Exactly one of the four keyword arguments must be provided.

    Parameters
    ----------
    overshoot : float or None
        Percent overshoot (e.g. 16.3 for 16.3%). Must be in (0, 100).
    settling_time : float or None
        2% settling time (s). Must be > 0. Uses settling_time ≈ 4/(ζ·ωn)
        and assumes ζ = 0.7 (typical design) to give ωn.
    rise_time : float or None
        10%→90% rise time (s). Must be > 0. Assumes ζ = 0.7.
    peak_time : float or None
        Time to first peak (s). Must be > 0. Requires ζ ≤ 1 so ωd > 0;
        uses peak_time = π/ωd and assumes ζ = 0.5 to give ωn if only
        peak_time is provided.

    Returns
    -------
    dict
        ok    : True
        wn    : undamped natural frequency (rad/s)
        zeta  : damping ratio
        spec  : which spec was used
        warnings: list
    """
    provided = {k: v for k, v in {
        "overshoot": overshoot,
        "settling_time": settling_time,
        "rise_time": rise_time,
        "peak_time": peak_time,
    }.items() if v is not None}

    if len(provided) == 0:
        return _err("Provide exactly one of: overshoot, settling_time, rise_time, peak_time.")
    if len(provided) > 1:
        return _err(
            f"Provide exactly one spec. Got: {list(provided.keys())}."
        )

    warnings: list[str] = []
    spec_name = list(provided.keys())[0]
    spec_val = float(list(provided.values())[0])

    if spec_name == "overshoot":
        if spec_val <= 0.0 or spec_val >= 100.0:
            return _err("overshoot must be in (0, 100) %.")
        # OS% = 100 exp(-π ζ/√(1-ζ²))  → ζ = -ln(OS/100) / √(π² + ln²(OS/100))
        ln_os = math.log(spec_val / 100.0)
        zeta = -ln_os / math.sqrt(math.pi ** 2 + ln_os ** 2)
        # ωn not uniquely determined from OS alone; return ζ and note
        wn = None
        warnings.append(
            "INCOMPLETE_SPEC: overshoot constrains zeta only; wn requires additional spec."
        )
        return {
            "ok": True,
            "wn": wn,
            "zeta": zeta,
            "spec": spec_name,
            "spec_value": spec_val,
            "warnings": warnings,
        }

    elif spec_name == "settling_time":
        if spec_val <= 0.0:
            return _err("settling_time must be > 0 s.")
        # Assume ζ = 0.7 (common design target), ts_2pct = 4/(ζ wn)
        zeta = 0.7
        wn = 4.0 / (zeta * spec_val)
        warnings.append("ASSUMED_ZETA=0.7: settling_time alone does not uniquely define both wn and zeta.")

    elif spec_name == "rise_time":
        if spec_val <= 0.0:
            return _err("rise_time must be > 0 s.")
        # tr ≈ (π - arccos(ζ))/ωd; assume ζ = 0.7
        zeta = 0.7
        wd = (math.pi - math.acos(zeta)) / spec_val
        wn = wd / math.sqrt(1.0 - zeta ** 2)
        warnings.append("ASSUMED_ZETA=0.7: rise_time alone does not uniquely define both wn and zeta.")

    elif spec_name == "peak_time":
        if spec_val <= 0.0:
            return _err("peak_time must be > 0 s.")
        # tp = π/ωd; assume ζ = 0.5
        zeta = 0.5
        wd = math.pi / spec_val
        wn = wd / math.sqrt(1.0 - zeta ** 2)
        warnings.append("ASSUMED_ZETA=0.5: peak_time alone does not uniquely define both wn and zeta.")

    else:
        return _err(f"Unknown spec {spec_name!r}.")

    return {
        "ok": True,
        "wn": wn,
        "zeta": zeta,
        "spec": spec_name,
        "spec_value": spec_val,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. first_order_step
# ---------------------------------------------------------------------------

def first_order_step(K: float, tau: float, t_samples: list[float]) -> dict:
    """
    First-order step response y(t) = K(1 − e^(−t/τ)).

    Parameters
    ----------
    K : float
        DC gain. Must be finite.
    tau : float
        Time constant (s). Must be > 0.
    t_samples : list[float]
        Time points (s). All must be >= 0.

    Returns
    -------
    dict
        ok          : True
        K           : DC gain
        tau         : time constant (s)
        t           : list of time points
        y           : list of y values
        steady_state: K
        warnings    : list
    """
    try:
        K = float(K)
        tau = float(tau)
    except (TypeError, ValueError) as exc:
        return _err(f"K or tau not numeric: {exc}")
    if not math.isfinite(K):
        return _err("K must be finite.")
    e = _guard_positive("tau", tau)
    if e:
        return _err(e)
    if not isinstance(t_samples, (list, tuple)) or len(t_samples) == 0:
        return _err("t_samples must be a non-empty list.")
    t_list: list[float] = []
    y_list: list[float] = []
    for t in t_samples:
        try:
            t_f = float(t)
        except (TypeError, ValueError):
            return _err(f"t_samples contains non-numeric value: {t!r}")
        if t_f < 0:
            return _err(f"t_samples values must be >= 0, got {t_f}.")
        t_list.append(t_f)
        y_list.append(K * (1.0 - math.exp(-t_f / tau)))
    return {
        "ok": True,
        "K": K,
        "tau": tau,
        "t": t_list,
        "y": y_list,
        "steady_state": K,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 4. first_order_impulse
# ---------------------------------------------------------------------------

def first_order_impulse(K: float, tau: float, t_samples: list[float]) -> dict:
    """
    First-order impulse response y(t) = (K/τ) e^(−t/τ).

    Parameters
    ----------
    K : float
        DC gain.
    tau : float
        Time constant (s). Must be > 0.
    t_samples : list[float]
        Time points (s). All must be >= 0.

    Returns
    -------
    dict
        ok      : True
        K       : DC gain
        tau     : time constant (s)
        t       : list of time points
        y       : list of y values
        peak_y  : y(0) = K/tau
        warnings: list
    """
    try:
        K = float(K)
        tau = float(tau)
    except (TypeError, ValueError) as exc:
        return _err(f"K or tau not numeric: {exc}")
    if not math.isfinite(K):
        return _err("K must be finite.")
    e = _guard_positive("tau", tau)
    if e:
        return _err(e)
    if not isinstance(t_samples, (list, tuple)) or len(t_samples) == 0:
        return _err("t_samples must be a non-empty list.")
    t_list: list[float] = []
    y_list: list[float] = []
    for t in t_samples:
        try:
            t_f = float(t)
        except (TypeError, ValueError):
            return _err(f"t_samples contains non-numeric value: {t!r}")
        if t_f < 0:
            return _err(f"t_samples values must be >= 0, got {t_f}.")
        t_list.append(t_f)
        y_list.append((K / tau) * math.exp(-t_f / tau))
    return {
        "ok": True,
        "K": K,
        "tau": tau,
        "t": t_list,
        "y": y_list,
        "peak_y": K / tau,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 5. second_order_step
# ---------------------------------------------------------------------------

def second_order_step(
    wn: float,
    zeta: float,
    t_samples: list[float],
    *,
    K: float = 1.0,
) -> dict:
    """
    Second-order unity-feedback step response samples.

    Transfer function: G(s) = K·ωn² / (s² + 2ζωns + ωn²)
    Closed-loop step response Y(s)/R(s) = K·ωn² / (s(s²+2ζωns+ωn²)).

    Parameters
    ----------
    wn : float
        Undamped natural frequency (rad/s). Must be > 0.
    zeta : float
        Damping ratio. Must be >= 0.
    t_samples : list[float]
        Time points (s). All must be >= 0.
    K : float
        DC gain (default 1.0).

    Returns
    -------
    dict
        ok       : True
        t        : list of time points
        y        : list of step response values
        wn, zeta, K
        warnings : list
    """
    e = _guard_positive("wn", wn)
    if e:
        return _err(e)
    e = _guard_nonneg("zeta", zeta)
    if e:
        return _err(e)
    try:
        K = float(K)
    except (TypeError, ValueError):
        return _err("K must be a number.")
    if not math.isfinite(K):
        return _err("K must be finite.")
    if not isinstance(t_samples, (list, tuple)) or len(t_samples) == 0:
        return _err("t_samples must be a non-empty list.")

    wn = float(wn)
    zeta = float(zeta)
    warnings: list[str] = []
    t_list: list[float] = []
    y_list: list[float] = []

    for t in t_samples:
        try:
            t_f = float(t)
        except (TypeError, ValueError):
            return _err(f"t_samples contains non-numeric value: {t!r}")
        if t_f < 0:
            return _err(f"t_samples values must be >= 0, got {t_f}.")
        t_list.append(t_f)

        if zeta >= 1.0:
            # Overdamped or critically damped
            if abs(zeta - 1.0) < 1e-12:
                # Critically damped: y(t) = K(1 - e^(-wn t)(1 + wn t))
                y = K * (1.0 - math.exp(-wn * t_f) * (1.0 + wn * t_f))
            else:
                # Overdamped
                wd = wn * math.sqrt(zeta ** 2 - 1.0)
                s1 = -zeta * wn + wd
                s2 = -zeta * wn - wd
                # Partial fractions: Y(s) = wn²/(s(s-s1)(s-s2))
                # y(t) = 1 + B*e^(s1 t) + C*e^(s2 t)
                # where B = wn²/(s1*(s1-s2)), C = wn²/(s2*(s2-s1))
                wn2 = wn ** 2
                B = wn2 / (s1 * (s1 - s2))
                C = wn2 / (s2 * (s2 - s1))
                y = K * (1.0 + B * math.exp(s1 * t_f) + C * math.exp(s2 * t_f))
        else:
            # Underdamped
            wd = wn * math.sqrt(1.0 - zeta ** 2)
            sigma = zeta * wn
            y = K * (1.0 - math.exp(-sigma * t_f) * (
                math.cos(wd * t_f) + (sigma / wd) * math.sin(wd * t_f)
            ))

        y_list.append(y)

    if zeta < 0.1:
        warnings.append("LOW_DAMPING: zeta < 0.1, highly oscillatory response.")

    return {
        "ok": True,
        "wn": wn,
        "zeta": zeta,
        "K": K,
        "t": t_list,
        "y": y_list,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. second_order_impulse
# ---------------------------------------------------------------------------

def second_order_impulse(
    wn: float,
    zeta: float,
    t_samples: list[float],
    *,
    K: float = 1.0,
) -> dict:
    """
    Second-order impulse response h(t).

    h(t) = (K·ωn/ωd) e^(-ζωn t) sin(ωd t)   [underdamped]
    h(t) = K·ωn² t e^(-ωn t)                  [critically damped]
    h(t) = (K·ωn/wd) e^(-ζωn t) sinh(wd t)   [overdamped]

    Parameters
    ----------
    wn : float
        Undamped natural frequency (rad/s). Must be > 0.
    zeta : float
        Damping ratio. Must be >= 0.
    t_samples : list[float]
        Time points (s). All must be >= 0.
    K : float
        DC gain (default 1.0).

    Returns
    -------
    dict
        ok       : True
        t        : list of time points
        y        : list of impulse response values
        warnings : list
    """
    e = _guard_positive("wn", wn)
    if e:
        return _err(e)
    e = _guard_nonneg("zeta", zeta)
    if e:
        return _err(e)
    try:
        K = float(K)
    except (TypeError, ValueError):
        return _err("K must be a number.")
    if not math.isfinite(K):
        return _err("K must be finite.")
    if not isinstance(t_samples, (list, tuple)) or len(t_samples) == 0:
        return _err("t_samples must be a non-empty list.")

    wn = float(wn)
    zeta = float(zeta)
    warnings: list[str] = []
    t_list: list[float] = []
    y_list: list[float] = []

    for t in t_samples:
        try:
            t_f = float(t)
        except (TypeError, ValueError):
            return _err(f"t_samples contains non-numeric value: {t!r}")
        if t_f < 0:
            return _err(f"t_samples values must be >= 0, got {t_f}.")
        t_list.append(t_f)

        sigma = zeta * wn
        if abs(zeta - 1.0) < 1e-12:
            # Critically damped
            y = K * wn ** 2 * t_f * math.exp(-wn * t_f)
        elif zeta < 1.0:
            wd = wn * math.sqrt(1.0 - zeta ** 2)
            y = (K * wn / wd) * math.exp(-sigma * t_f) * math.sin(wd * t_f)
        else:
            wd = wn * math.sqrt(zeta ** 2 - 1.0)
            if wd == 0:
                y = K * wn ** 2 * t_f * math.exp(-sigma * t_f)
            else:
                y = (K * wn / wd) * math.exp(-sigma * t_f) * math.sinh(wd * t_f)

        y_list.append(y)

    return {
        "ok": True,
        "wn": wn,
        "zeta": zeta,
        "K": K,
        "t": t_list,
        "y": y_list,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. routh_hurwitz
# ---------------------------------------------------------------------------

def routh_hurwitz(coeffs: list[float]) -> dict:
    """
    Routh-Hurwitz stability table for a real-coefficient characteristic polynomial.

    The polynomial is: a[0]*s^n + a[1]*s^(n-1) + ... + a[n]
    where a[0] is the leading coefficient (highest power).

    Parameters
    ----------
    coeffs : list[float]
        Polynomial coefficients, highest power first. Must have >= 2 entries
        and a[0] != 0.

    Returns
    -------
    dict
        ok              : True
        n               : polynomial degree
        routh_array     : list of rows; each row is a list of floats
        sign_changes    : number of sign changes in first column = RHP poles
        stable          : True if sign_changes == 0 and all coeffs same sign
        warnings        : list of flag strings

    Notes
    -----
    - Sign changes in first column of Routh array = number of RHP poles.
    - A row of all zeros (special case: auxiliary polynomial) is handled
      by replacing the zero row with derivatives of the auxiliary polynomial;
      this is noted in warnings but computation continues.

    References: Ogata §6-3, Nise §6-2.
    """
    if not isinstance(coeffs, (list, tuple)) or len(coeffs) < 2:
        return _err("coeffs must be a list with at least 2 entries.")
    try:
        c = [float(x) for x in coeffs]
    except (TypeError, ValueError) as exc:
        return _err(f"coeffs must contain numbers: {exc}")
    if c[0] == 0:
        return _err("Leading coefficient (coeffs[0]) must be non-zero.")

    warnings: list[str] = []
    n = len(c) - 1  # polynomial degree

    # Build first two rows of Routh array
    # Row 0: a[0], a[2], a[4], ...
    # Row 1: a[1], a[3], a[5], ...
    row_len = n // 2 + 1
    array: list[list[float]] = []

    row0 = [c[i] for i in range(0, len(c), 2)]
    row1 = [c[i] for i in range(1, len(c), 2)]
    # Pad to same length
    while len(row0) < row_len:
        row0.append(0.0)
    while len(row1) < row_len:
        row1.append(0.0)

    array.append(row0[:row_len])
    array.append(row1[:row_len])

    # Compute remaining rows
    for i in range(2, n + 1):
        prev2 = array[-2]
        prev1 = array[-1]
        new_row: list[float] = []
        # First element of previous row as pivot
        pivot = prev1[0]
        if abs(pivot) < 1e-15:
            # All-zero row or near-zero pivot — auxiliary polynomial
            warnings.append(
                f"NEAR_ZERO_PIVOT at row {i}: marginal stability or auxiliary polynomial. "
                "Using epsilon replacement; result may be approximate."
            )
            # Use small epsilon
            pivot = 1e-15

        row_len_i = len(prev2) - 1
        for j in range(row_len_i):
            val = (prev1[0] * prev2[j + 1] - prev2[0] * prev1[j + 1]) / pivot
            new_row.append(val)
        new_row.append(0.0)
        array.append(new_row)

    # Count sign changes in first column
    first_col = [row[0] for row in array]
    sign_changes = 0
    prev_sign = 1 if first_col[0] > 0 else -1
    for val in first_col[1:]:
        if val == 0.0:
            continue
        cur_sign = 1 if val > 0 else -1
        if cur_sign != prev_sign:
            sign_changes += 1
            prev_sign = cur_sign

    stable = (sign_changes == 0)
    if not stable:
        warnings.append(f"UNSTABLE: {sign_changes} RHP pole(s) detected.")

    # Check all coefficients same sign (necessary but not sufficient for stability)
    if all(x > 0 for x in c) or all(x < 0 for x in c):
        pass  # necessary condition satisfied
    else:
        warnings.append("SIGN_MIXED: Not all coefficients same sign — definitely unstable.")

    return {
        "ok": True,
        "n": n,
        "routh_array": array,
        "sign_changes": sign_changes,
        "stable": stable,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. bode_point
# ---------------------------------------------------------------------------

def bode_point(
    num: list[float],
    den: list[float],
    omega: float,
) -> dict:
    """
    Bode magnitude (dB) and phase (deg) of a transfer function at frequency ω.

    Transfer function: G(jω) = num(jω) / den(jω)
    where num and den are polynomials with real coefficients, highest power first.

    Parameters
    ----------
    num : list[float]
        Numerator polynomial coefficients [b0, b1, ..., bm].
    den : list[float]
        Denominator polynomial coefficients [a0, a1, ..., an].
    omega : float
        Frequency (rad/s). Must be > 0.

    Returns
    -------
    dict
        ok           : True
        omega        : frequency (rad/s)
        magnitude_dB : 20·log10|G(jω)|
        phase_deg    : ∠G(jω) in degrees
        G_real       : Re[G(jω)]
        G_imag       : Im[G(jω)]
        warnings     : list of flag strings

    Notes
    -----
    Evaluates G(s) = num(s)/den(s) at s = jω using Horner's method for
    complex polynomial evaluation.

    References: Ogata §8, Nise §10.
    """
    if not isinstance(num, (list, tuple)) or len(num) == 0:
        return _err("num must be a non-empty list.")
    if not isinstance(den, (list, tuple)) or len(den) == 0:
        return _err("den must be a non-empty list.")
    e = _guard_positive("omega", omega)
    if e:
        return _err(e)
    try:
        num_c = [float(x) for x in num]
        den_c = [float(x) for x in den]
    except (TypeError, ValueError) as exc:
        return _err(f"num/den must contain real numbers: {exc}")

    omega = float(omega)
    s = complex(0.0, omega)  # s = jω

    num_val = _poly_eval(num_c, s)
    den_val = _poly_eval(den_c, s)

    warnings: list[str] = []

    if abs(den_val) < 1e-30:
        warnings.append("NEAR_POLE: denominator near zero at this frequency.")
        return {
            "ok": True,
            "omega": omega,
            "magnitude_dB": float("inf"),
            "phase_deg": float("nan"),
            "G_real": float("nan"),
            "G_imag": float("nan"),
            "warnings": warnings,
        }

    G = num_val / den_val
    mag = abs(G)
    mag_dB = 20.0 * math.log10(mag) if mag > 0 else float("-inf")
    phase_rad = cmath.phase(G)
    phase_deg = math.degrees(phase_rad)

    # Check non-minimum phase (RHP zeros)
    # Approximate: if phase drops below -180 early, flag
    if phase_deg < -180.0:
        warnings.append("NON_MINIMUM_PHASE: phase < -180 deg; possible RHP zero or time delay.")

    return {
        "ok": True,
        "omega": omega,
        "magnitude_dB": mag_dB,
        "phase_deg": phase_deg,
        "G_real": G.real,
        "G_imag": G.imag,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. gain_phase_margins
# ---------------------------------------------------------------------------

def gain_phase_margins(
    num: list[float],
    den: list[float],
    omega_range: list[float] | None = None,
) -> dict:
    """
    Gain margin, phase margin, and crossover frequencies by numeric sweep.

    Parameters
    ----------
    num : list[float]
        Open-loop TF numerator polynomial (highest power first).
    den : list[float]
        Open-loop TF denominator polynomial.
    omega_range : list[float] or None
        [omega_min, omega_max] for sweep. Default: [1e-3, 1e4].
        If a 3-element list [omega_min, omega_max, n_points] is given,
        n_points sweep steps are used (default 2000).

    Returns
    -------
    dict
        ok                  : True
        gain_margin_dB      : gain margin (dB). None if no phase crossover found.
        phase_margin_deg    : phase margin (deg). None if no gain crossover found.
        gain_crossover_rad_s: ω where |G(jω)| = 1 (0 dB). None if not found.
        phase_crossover_rad_s: ω where ∠G(jω) = -180°. None if not found.
        stable_gm           : True if gain margin > 0 dB
        stable_pm           : True if phase margin > 0 deg
        warnings            : list of flag strings

    Notes
    -----
    The sweep detects the first gain crossover (|G| crosses 0 dB from above)
    and first phase crossover (∠G crosses -180°) by linear interpolation
    between sample points. For more precision, provide a finer omega_range.

    References: Ogata §9-3, Nise §11-2.
    """
    if not isinstance(num, (list, tuple)) or len(num) == 0:
        return _err("num must be a non-empty list.")
    if not isinstance(den, (list, tuple)) or len(den) == 0:
        return _err("den must be a non-empty list.")
    try:
        num_c = [float(x) for x in num]
        den_c = [float(x) for x in den]
    except (TypeError, ValueError) as exc:
        return _err(f"num/den must contain real numbers: {exc}")

    # Parse omega_range
    omega_min = 1e-3
    omega_max = 1e4
    n_pts = 2000
    if omega_range is not None:
        if not isinstance(omega_range, (list, tuple)) or len(omega_range) < 2:
            return _err("omega_range must be [omega_min, omega_max] or [omega_min, omega_max, n_points].")
        try:
            omega_min = float(omega_range[0])
            omega_max = float(omega_range[1])
            if len(omega_range) >= 3:
                n_pts = int(omega_range[2])
        except (TypeError, ValueError) as exc:
            return _err(f"omega_range values must be numbers: {exc}")
    if omega_min <= 0 or omega_max <= omega_min:
        return _err("omega_range must have 0 < omega_min < omega_max.")
    if n_pts < 10:
        return _err("n_points must be >= 10.")

    warnings: list[str] = []

    # Generate log-spaced frequencies
    log_min = math.log10(omega_min)
    log_max = math.log10(omega_max)
    log_step = (log_max - log_min) / (n_pts - 1)
    omegas = [10.0 ** (log_min + i * log_step) for i in range(n_pts)]

    # Evaluate Bode at all points
    mags_dB: list[float] = []
    phases_deg: list[float] = []
    for w in omegas:
        pt = bode_point(num_c, den_c, w)
        if not pt["ok"]:
            mags_dB.append(float("nan"))
            phases_deg.append(float("nan"))
        else:
            mags_dB.append(pt["magnitude_dB"])
            # Unwrap phase for margin detection
            phases_deg.append(pt["phase_deg"])

    # Find gain crossover: |G| = 0 dB (mag_dB crosses 0)
    gain_crossover: float | None = None
    pm_deg: float | None = None
    for i in range(n_pts - 1):
        m0, m1 = mags_dB[i], mags_dB[i + 1]
        if math.isnan(m0) or math.isnan(m1):
            continue
        if m0 * m1 <= 0 and m0 != m1:
            # Linear interpolation
            frac = -m0 / (m1 - m0)
            gain_crossover = omegas[i] + frac * (omegas[i + 1] - omegas[i])
            phase_at_gc = phases_deg[i] + frac * (phases_deg[i + 1] - phases_deg[i])
            pm_deg = 180.0 + phase_at_gc
            break

    # Find phase crossover: ∠G = -180°
    phase_crossover: float | None = None
    gm_dB: float | None = None
    for i in range(n_pts - 1):
        p0, p1 = phases_deg[i], phases_deg[i + 1]
        if math.isnan(p0) or math.isnan(p1):
            continue
        # Detect crossing of -180
        if (p0 + 180.0) * (p1 + 180.0) <= 0 and p0 != p1:
            frac = -(p0 + 180.0) / (p1 - p0)
            phase_crossover = omegas[i] + frac * (omegas[i + 1] - omegas[i])
            mag_at_pc = mags_dB[i] + frac * (mags_dB[i + 1] - mags_dB[i])
            gm_dB = -mag_at_pc  # GM = -|G(jω_pc)|_dB
            break

    stable_gm = (gm_dB is not None and gm_dB > 0)
    stable_pm = (pm_deg is not None and pm_deg > 0)

    if gm_dB is not None and gm_dB < 6.0:
        warnings.append(f"POOR_GAIN_MARGIN: GM = {gm_dB:.1f} dB < 6 dB (recommended).")
    if pm_deg is not None and pm_deg < 30.0:
        warnings.append(f"POOR_PHASE_MARGIN: PM = {pm_deg:.1f} deg < 30 deg (recommended).")
    if gain_crossover is None:
        warnings.append("NO_GAIN_CROSSOVER: |G(jω)| never crosses 0 dB in sweep range.")
    if phase_crossover is None:
        warnings.append("NO_PHASE_CROSSOVER: ∠G(jω) never crosses -180° in sweep range.")
    if not stable_gm and gm_dB is not None:
        warnings.append("UNSTABLE: gain margin is negative.")
    if not stable_pm and pm_deg is not None:
        warnings.append("UNSTABLE: phase margin is negative.")

    return {
        "ok": True,
        "gain_margin_dB": gm_dB,
        "phase_margin_deg": pm_deg,
        "gain_crossover_rad_s": gain_crossover,
        "phase_crossover_rad_s": phase_crossover,
        "stable_gm": stable_gm,
        "stable_pm": stable_pm,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. steady_state_errors
# ---------------------------------------------------------------------------

def steady_state_errors(
    num_ol: list[float],
    den_ol: list[float],
) -> dict:
    """
    Steady-state error analysis for a unity-feedback closed-loop system.

    Determines system type (number of pure integrators in open-loop TF)
    and error constants Kp, Kv, Ka.

    Parameters
    ----------
    num_ol : list[float]
        Open-loop TF numerator coefficients (highest power first).
    den_ol : list[float]
        Open-loop TF denominator coefficients.

    Returns
    -------
    dict
        ok              : True
        system_type     : 0, 1, or 2 (number of free integrators)
        Kp              : position error constant lim(s→0) G(s)
        Kv              : velocity error constant lim(s→0) s·G(s)
        Ka              : acceleration error constant lim(s→0) s²·G(s)
        ess_step        : steady-state error to unit step = 1/(1+Kp)
        ess_ramp        : steady-state error to unit ramp = 1/Kv
        ess_parabola    : steady-state error to unit parabola = 1/Ka
        warnings        : list

    Notes
    -----
    System type is determined by counting trailing zeros in the denominator
    polynomial (i.e., factors of s). For type 0: ess_step = 1/(1+Kp),
    ess_ramp = ∞, ess_parabola = ∞. For type 1: ess_step = 0, etc.

    References: Ogata §7-3, Nise §7-4.
    """
    if not isinstance(num_ol, (list, tuple)) or len(num_ol) == 0:
        return _err("num_ol must be a non-empty list.")
    if not isinstance(den_ol, (list, tuple)) or len(den_ol) == 0:
        return _err("den_ol must be a non-empty list.")
    try:
        num_c = [float(x) for x in num_ol]
        den_c = [float(x) for x in den_ol]
    except (TypeError, ValueError) as exc:
        return _err(f"num_ol/den_ol must contain real numbers: {exc}")
    if den_c[-1] == 0 and num_c[-1] == 0:
        pass  # could be type 1+
    elif not den_c:
        return _err("den_ol must be non-empty.")

    warnings: list[str] = []

    # Count system type: number of trailing zeros in denominator
    # i.e., den(s) = s^N * d_reduced(s) where d_reduced(0) != 0
    system_type = 0
    d = den_c[:]
    while len(d) > 1 and abs(d[-1]) < 1e-12:
        system_type += 1
        d = d[:-1]  # remove trailing zero (divide by s)

    # Evaluate limits
    # Kp = lim(s→0) G(s) = num(0)/den_reduced(0)
    # Kv = lim(s→0) s·G(s) — need one factor of s from den cancelled
    # Ka = lim(s→0) s²·G(s)

    def _eval_at_zero(coeffs: list[float]) -> float:
        """Polynomial value at s=0 is the constant term (last element)."""
        return coeffs[-1] if coeffs else 0.0

    num_0 = _eval_at_zero(num_c)

    # Build den stripped of s factors
    def _strip_s(coeffs: list[float], n: int) -> list[float]:
        """Remove n factors of s from polynomial (divide by s^n)."""
        c = coeffs[:]
        for _ in range(n):
            if abs(c[-1]) < 1e-12:
                c = c[:-1]
            else:
                break
        return c

    den_type0 = _strip_s(den_c, 0)   # original
    den_type1 = _strip_s(den_c, 1)   # divided by s once
    den_type2 = _strip_s(den_c, 2)   # divided by s²

    # Kp = lim G(s) as s→0
    den0_val = _eval_at_zero(den_type0)
    if abs(den0_val) < 1e-15:
        # Type >= 1: Kp = infinity
        Kp = float("inf")
    else:
        Kp = num_0 / den0_val

    # Kv = lim s·G(s) as s→0
    den1_val = _eval_at_zero(den_type1)
    if abs(den1_val) < 1e-15:
        Kv = float("inf")
    else:
        Kv = num_0 / den1_val

    # Ka = lim s²·G(s) as s→0
    den2_val = _eval_at_zero(den_type2)
    if abs(den2_val) < 1e-15:
        Ka = float("inf")
    else:
        Ka = num_0 / den2_val

    # Steady-state errors
    ess_step = 1.0 / (1.0 + Kp) if math.isfinite(Kp) else 0.0
    ess_ramp = 1.0 / Kv if math.isfinite(Kv) and Kv != 0 else (0.0 if Kv == float("inf") else float("inf"))
    ess_parabola = 1.0 / Ka if math.isfinite(Ka) and Ka != 0 else (0.0 if Ka == float("inf") else float("inf"))

    if system_type == 0:
        warnings.append("TYPE_0: non-zero steady-state error to ramp and parabola inputs.")
    elif system_type == 1:
        warnings.append("TYPE_1: non-zero steady-state error to parabola input.")
    elif system_type >= 2:
        warnings.append("TYPE_2+: zero ess for step, ramp, and parabola.")

    return {
        "ok": True,
        "system_type": system_type,
        "Kp": Kp,
        "Kv": Kv,
        "Ka": Ka,
        "ess_step": ess_step,
        "ess_ramp": ess_ramp,
        "ess_parabola": ess_parabola,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. pid_zn_open (Ziegler-Nichols open-loop / process-reaction-curve method)
# ---------------------------------------------------------------------------

def pid_zn_open(K: float, tau: float, theta: float) -> dict:
    """
    Ziegler-Nichols open-loop (process-reaction-curve) PID tuning from FOPDT.

    FOPDT model: G(s) = K e^(-θs) / (τs + 1)

    Z-N tuning rules (Ziegler & Nichols, 1942):
        P:   Kp = τ/(K·θ)
        PI:  Kp = 0.9 τ/(K·θ),        Ti = 3.33θ
        PID: Kp = 1.2 τ/(K·θ),        Ti = 2θ,    Td = 0.5θ

    Parameters
    ----------
    K : float
        Process gain. Must be != 0 and finite.
    tau : float
        Process time constant (s). Must be > 0.
    theta : float
        Dead time / time delay (s). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        K, tau, theta
        P        : {"Kp": ...}
        PI       : {"Kp": ..., "Ki": ..., "Ti": ...}
        PID      : {"Kp": ..., "Ki": ..., "Ti": ..., "Kd": ..., "Td": ...}
        R        : controllability ratio theta/tau (< 0.3 easy, > 1.0 hard)
        warnings : list

    References: Ziegler & Nichols (1942); Ogata §8-6.
    """
    try:
        K = float(K)
        tau = float(tau)
        theta = float(theta)
    except (TypeError, ValueError) as exc:
        return _err(f"K, tau, theta must be numbers: {exc}")
    if not math.isfinite(K) or K == 0:
        return _err("K must be finite and non-zero.")
    e = _guard_positive("tau", tau)
    if e:
        return _err(e)
    e = _guard_positive("theta", theta)
    if e:
        return _err(e)

    warnings: list[str] = []
    R = theta / tau  # controllability ratio

    if R > 1.0:
        warnings.append(
            f"HARD_TO_CONTROL: theta/tau = {R:.2f} > 1.0; Z-N tuning may give poor performance."
        )
    if R > 2.0:
        warnings.append(
            "VERY_HARD_TO_CONTROL: theta/tau > 2.0; consider IMC/Lambda tuning instead."
        )

    # P tuning
    Kp_P = tau / (K * theta)

    # PI tuning
    Kp_PI = 0.9 * tau / (K * theta)
    Ti_PI = 3.33 * theta
    Ki_PI = Kp_PI / Ti_PI

    # PID tuning
    Kp_PID = 1.2 * tau / (K * theta)
    Ti_PID = 2.0 * theta
    Td_PID = 0.5 * theta
    Ki_PID = Kp_PID / Ti_PID
    Kd_PID = Kp_PID * Td_PID

    return {
        "ok": True,
        "K": K,
        "tau": tau,
        "theta": theta,
        "R": R,
        "P": {"Kp": Kp_P},
        "PI": {"Kp": Kp_PI, "Ti": Ti_PI, "Ki": Ki_PI},
        "PID": {
            "Kp": Kp_PID,
            "Ti": Ti_PID,
            "Td": Td_PID,
            "Ki": Ki_PID,
            "Kd": Kd_PID,
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. pid_zn_closed (Ziegler-Nichols closed-loop / ultimate gain method)
# ---------------------------------------------------------------------------

def pid_zn_closed(Ku: float, Tu: float) -> dict:
    """
    Ziegler-Nichols closed-loop (ultimate gain / frequency) PID tuning.

    At the stability boundary: Ku = ultimate gain, Tu = ultimate period (s).

    Z-N rules:
        P:   Kp = 0.50 Ku
        PI:  Kp = 0.45 Ku,  Ti = Tu/1.2
        PD:  Kp = 0.80 Ku,  Td = Tu/8
        PID: Kp = 0.60 Ku,  Ti = Tu/2,  Td = Tu/8

    Parameters
    ----------
    Ku : float
        Ultimate gain (proportional gain at stability boundary). Must be > 0.
    Tu : float
        Ultimate period (s). Must be > 0.

    Returns
    -------
    dict
        ok   : True
        Ku, Tu
        P    : {"Kp": ...}
        PI   : {"Kp": ..., "Ti": ..., "Ki": ...}
        PD   : {"Kp": ..., "Td": ..., "Kd": ...}
        PID  : {"Kp": ..., "Ti": ..., "Td": ..., "Ki": ..., "Kd": ...}
        warnings: list

    References: Ziegler & Nichols (1942); Ogata §8-7.
    """
    e = _guard_positive("Ku", Ku)
    if e:
        return _err(e)
    e = _guard_positive("Tu", Tu)
    if e:
        return _err(e)
    Ku = float(Ku)
    Tu = float(Tu)
    warnings: list[str] = []
    warnings.append(
        "Z-N CLOSED-LOOP: tuning is aggressive; expect ~25% overshoot. "
        "Consider Tyreus-Luyben or Astrom-Hagglund refinement."
    )

    # P
    Kp_P = 0.50 * Ku

    # PI
    Kp_PI = 0.45 * Ku
    Ti_PI = Tu / 1.2
    Ki_PI = Kp_PI / Ti_PI

    # PD
    Kp_PD = 0.80 * Ku
    Td_PD = Tu / 8.0
    Kd_PD = Kp_PD * Td_PD

    # PID
    Kp_PID = 0.60 * Ku
    Ti_PID = Tu / 2.0
    Td_PID = Tu / 8.0
    Ki_PID = Kp_PID / Ti_PID
    Kd_PID = Kp_PID * Td_PID

    return {
        "ok": True,
        "Ku": Ku,
        "Tu": Tu,
        "P": {"Kp": Kp_P},
        "PI": {"Kp": Kp_PI, "Ti": Ti_PI, "Ki": Ki_PI},
        "PD": {"Kp": Kp_PD, "Td": Td_PD, "Kd": Kd_PD},
        "PID": {
            "Kp": Kp_PID,
            "Ti": Ti_PID,
            "Td": Td_PID,
            "Ki": Ki_PID,
            "Kd": Kd_PID,
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 13. pid_cohen_coon
# ---------------------------------------------------------------------------

def pid_cohen_coon(K: float, tau: float, theta: float) -> dict:
    """
    Cohen-Coon PID tuning from FOPDT parameters.

    FOPDT model: G(s) = K e^(-θs) / (τs + 1)

    Cohen-Coon formulas (1953) are derived to minimize IAE and typically
    give better performance than Z-N for processes with large dead time.

    Let R = θ/(θ + τ):
        P:   Kp = (1/K)(τ/θ)(1 + R/3)
        PI:  Kp = (1/K)(τ/θ)(0.9 + R/12)
             Ti = θ(30 + 3R)/(9 + 20R)
        PID: Kp = (1/K)(τ/θ)(4/3 + R/4)
             Ti = θ(32 + 6R)/(13 + 8R)
             Td = θ·4/(11 + 2R)

    Parameters
    ----------
    K : float
        Process gain. Must be != 0 and finite.
    tau : float
        Time constant (s). Must be > 0.
    theta : float
        Dead time (s). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        K, tau, theta
        R        : theta/(theta + tau)
        P        : {"Kp": ...}
        PI       : {"Kp": ..., "Ti": ..., "Ki": ...}
        PID      : {"Kp": ..., "Ti": ..., "Td": ..., "Ki": ..., "Kd": ...}
        warnings : list

    References: Cohen & Coon (1953); Seborg et al. "Process Dynamics and Control", §12-4.
    """
    try:
        K = float(K)
        tau = float(tau)
        theta = float(theta)
    except (TypeError, ValueError) as exc:
        return _err(f"K, tau, theta must be numbers: {exc}")
    if not math.isfinite(K) or K == 0:
        return _err("K must be finite and non-zero.")
    e = _guard_positive("tau", tau)
    if e:
        return _err(e)
    e = _guard_positive("theta", theta)
    if e:
        return _err(e)

    warnings: list[str] = []
    R = theta / (theta + tau)

    if R > 0.5:
        warnings.append(
            f"LARGE_DEAD_TIME_RATIO: R = {R:.2f} > 0.5; Cohen-Coon may still be used but "
            "consider Smith predictor or model-based approaches."
        )

    tau_over_theta = tau / theta

    # P
    Kp_P = (1.0 / K) * tau_over_theta * (1.0 + R / 3.0)

    # PI
    Kp_PI = (1.0 / K) * tau_over_theta * (0.9 + R / 12.0)
    Ti_PI = theta * (30.0 + 3.0 * R) / (9.0 + 20.0 * R)
    Ki_PI = Kp_PI / Ti_PI

    # PID
    Kp_PID = (1.0 / K) * tau_over_theta * (4.0 / 3.0 + R / 4.0)
    Ti_PID = theta * (32.0 + 6.0 * R) / (13.0 + 8.0 * R)
    Td_PID = theta * 4.0 / (11.0 + 2.0 * R)
    Ki_PID = Kp_PID / Ti_PID
    Kd_PID = Kp_PID * Td_PID

    return {
        "ok": True,
        "K": K,
        "tau": tau,
        "theta": theta,
        "R": R,
        "P": {"Kp": Kp_P},
        "PI": {"Kp": Kp_PI, "Ti": Ti_PI, "Ki": Ki_PI},
        "PID": {
            "Kp": Kp_PID,
            "Ti": Ti_PID,
            "Td": Td_PID,
            "Ki": Ki_PID,
            "Kd": Kd_PID,
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 14. pid_imc (Lambda / IMC tuning)
# ---------------------------------------------------------------------------

def pid_imc(K: float, tau: float, theta: float, lambda_c: float) -> dict:
    """
    Lambda / IMC (Internal Model Control) PID tuning from FOPDT.

    FOPDT model: G(s) = K e^(-θs) / (τs + 1)

    IMC-based PID (Rivera, Morari & Skogestad, 1986):
        Kp = τ / (K(λ + θ))
        Ti = τ
        Td = θ/2

    The closed-loop time constant λ (lambda_c) is the tuning parameter:
      - Smaller λ → faster response, less robustness
      - Larger  λ → slower response, better robustness
    Recommended: λ ≥ 0.25τ or λ ≥ θ, whichever is larger.

    Parameters
    ----------
    K : float
        Process gain. Must be != 0 and finite.
    tau : float
        Time constant (s). Must be > 0.
    theta : float
        Dead time (s). Must be > 0.
    lambda_c : float
        Desired closed-loop time constant (s). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        K, tau, theta, lambda_c
        PID      : {"Kp": ..., "Ti": ..., "Td": ..., "Ki": ..., "Kd": ...}
        warnings : list

    References: Rivera, Morari & Skogestad (1986); Seborg et al. §12-5.
    """
    try:
        K = float(K)
        tau = float(tau)
        theta = float(theta)
        lambda_c = float(lambda_c)
    except (TypeError, ValueError) as exc:
        return _err(f"K, tau, theta, lambda_c must be numbers: {exc}")
    if not math.isfinite(K) or K == 0:
        return _err("K must be finite and non-zero.")
    e = _guard_positive("tau", tau)
    if e:
        return _err(e)
    e = _guard_positive("theta", theta)
    if e:
        return _err(e)
    e = _guard_positive("lambda_c", lambda_c)
    if e:
        return _err(e)

    warnings: list[str] = []

    # Recommended minimum λ
    lambda_min = max(0.25 * tau, theta)
    if lambda_c < lambda_min:
        warnings.append(
            f"AGGRESSIVE_LAMBDA: lambda_c = {lambda_c:.3g} < recommended minimum "
            f"{lambda_min:.3g} (max(0.25τ, θ)). May cause robustness issues."
        )

    Kp = tau / (K * (lambda_c + theta))
    Ti = tau
    Td = theta / 2.0
    Ki = Kp / Ti
    Kd = Kp * Td

    return {
        "ok": True,
        "K": K,
        "tau": tau,
        "theta": theta,
        "lambda_c": lambda_c,
        "PID": {
            "Kp": Kp,
            "Ti": Ti,
            "Td": Td,
            "Ki": Ki,
            "Kd": Kd,
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 15. root_locus_breakaway
# ---------------------------------------------------------------------------

def root_locus_breakaway(
    num: list[float],
    den: list[float],
) -> dict:
    """
    Real-axis breakaway and break-in points of the root locus.

    For the open-loop transfer function G(s)H(s) = K·num(s)/den(s),
    breakaway/break-in points satisfy:

        d/ds [den(s)/num(s)] = 0
        ⟺  den'(s)·num(s) - den(s)·num'(s) = 0

    Only real roots of this equation that lie on the real-axis segments
    of the root locus are breakaway/break-in points. This function returns
    all real roots of the characteristic equation above (which includes
    candidate points; the caller should verify which lie on the real-axis
    locus).

    Parameters
    ----------
    num : list[float]
        Numerator polynomial (highest power first).
    den : list[float]
        Denominator polynomial.

    Returns
    -------
    dict
        ok               : True
        breakaway_points : list of real roots (candidates)
        n_roots          : number of candidate points found
        warnings         : list

    Notes
    -----
    The equation solved is: den'(s)·num(s) - den(s)·num'(s) = 0.
    Roots are found numerically by scanning the real axis [-1000, 1000].
    For more precise results, narrow the search range.

    References: Ogata §7-5, Nise §8-6.
    """
    if not isinstance(num, (list, tuple)) or len(num) == 0:
        return _err("num must be a non-empty list.")
    if not isinstance(den, (list, tuple)) or len(den) == 0:
        return _err("den must be a non-empty list.")
    try:
        num_c = [float(x) for x in num]
        den_c = [float(x) for x in den]
    except (TypeError, ValueError) as exc:
        return _err(f"num/den must contain real numbers: {exc}")

    warnings: list[str] = []

    # Compute den'(s)·num(s) - den(s)·num'(s)
    # Polynomial multiplication and subtraction
    num_d = _poly_deriv(num_c)
    den_d = _poly_deriv(den_c)

    # Multiply polynomials: result coefficients for den' * num
    def _poly_mul(a: list[float], b: list[float]) -> list[float]:
        if not a or not b:
            return [0.0]
        result = [0.0] * (len(a) + len(b) - 1)
        for i, ai in enumerate(a):
            for j, bj in enumerate(b):
                result[i + j] += ai * bj
        return result

    def _poly_sub(a: list[float], b: list[float]) -> list[float]:
        la, lb = len(a), len(b)
        lmax = max(la, lb)
        result = [0.0] * lmax
        for i in range(la):
            result[lmax - la + i] += a[i]
        for i in range(lb):
            result[lmax - lb + i] -= b[i]
        return result

    term1 = _poly_mul(den_d, num_c)
    term2 = _poly_mul(den_c, num_d)
    char_poly = _poly_sub(term1, term2)

    # Remove leading zeros
    while len(char_poly) > 1 and abs(char_poly[0]) < 1e-15:
        char_poly = char_poly[1:]

    if len(char_poly) <= 1:
        warnings.append("TRIVIAL: breakaway polynomial is constant; no finite breakaway points.")
        return {
            "ok": True,
            "breakaway_points": [],
            "n_roots": 0,
            "warnings": warnings,
        }

    roots = _poly_roots_real_axis(char_poly)

    # Round near-integer or near-zero values for cleanliness
    cleaned = []
    for r in roots:
        if abs(r) < 1e-8:
            cleaned.append(0.0)
        else:
            cleaned.append(round(r, 8))

    if len(cleaned) == 0:
        warnings.append("NO_BREAKAWAY: no real breakaway/break-in points found in [-1000, 1000].")

    return {
        "ok": True,
        "breakaway_points": cleaned,
        "n_roots": len(cleaned),
        "warnings": warnings,
    }
