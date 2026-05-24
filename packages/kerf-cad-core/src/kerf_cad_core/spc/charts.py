"""
kerf_cad_core.spc.charts — Statistical Process Control (SPC) control charts.

Implements:
  * Shewhart X̄-R and X̄-S charts (subgroup mean + range / std-dev)
  * CUSUM (tabular / V-mask)
  * EWMA chart (λ smoothing, steady-state ±3σ limits)
  * Run-rule detection (Nelson rules 1–8 + Western Electric)

All chart functions are pure Python (no numpy).
Each returns a dict with control limits, per-subgroup statistics, and
flagged out-of-control points.

Constants
---------
Shewhart constants A2, A3, B3, B4, D3, D4 per ASTM E2587 / Montgomery
"Introduction to Statistical Quality Control" 8th ed., Table VI.

References
----------
Montgomery, D.C. (2020). Introduction to Statistical Quality Control, 8th ed.
ASTM E2587-16. Standard Practice for Use of Control Charts in SPC.
Nelson, L.S. (1984). "The Shewhart Control Chart — Tests for Special Causes."
    Journal of Quality Technology 16(4): 237-239.
Western Electric Company (1956). Statistical Quality Control Handbook.
Lucas, J.M. & Crosier, R.B. (1982). "Fast initial response for CUSUM
    quality-control schemes." Technometrics 24(3): 199-205.
Hunter, J.S. (1986). "The exponentially weighted moving average."
    Journal of Quality Technology 18(4): 203-210.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Shewhart constants (ASTM E2587 / Montgomery Table VI)
# Key: subgroup size n (2 … 25)
# ---------------------------------------------------------------------------

# fmt: off
_SHEWHART_CONSTANTS: dict[int, dict[str, float]] = {
    # n: {A2, A3, B3, B4, D3, D4, d2, c4}
    2:  {"A2": 1.880, "A3": 2.659, "B3": 0.000, "B4": 3.267, "D3": 0.000, "D4": 3.267, "d2": 1.128, "c4": 0.7979},
    3:  {"A2": 1.023, "A3": 1.954, "B3": 0.000, "B4": 2.568, "D3": 0.000, "D4": 2.574, "d2": 1.693, "c4": 0.8862},
    4:  {"A2": 0.729, "A3": 1.628, "B3": 0.000, "B4": 2.266, "D3": 0.000, "D4": 2.282, "d2": 2.059, "c4": 0.9213},
    5:  {"A2": 0.577, "A3": 1.427, "B3": 0.000, "B4": 2.089, "D3": 0.000, "D4": 2.114, "d2": 2.326, "c4": 0.9400},
    6:  {"A2": 0.483, "A3": 1.287, "B3": 0.030, "B4": 1.970, "D3": 0.000, "D4": 2.004, "d2": 2.534, "c4": 0.9515},
    7:  {"A2": 0.419, "A3": 1.182, "B3": 0.118, "B4": 1.882, "D3": 0.076, "D4": 1.924, "d2": 2.704, "c4": 0.9594},
    8:  {"A2": 0.373, "A3": 1.099, "B3": 0.185, "B4": 1.815, "D3": 0.136, "D4": 1.864, "d2": 2.847, "c4": 0.9650},
    9:  {"A2": 0.337, "A3": 1.032, "B3": 0.239, "B4": 1.761, "D3": 0.184, "D4": 1.816, "d2": 2.970, "c4": 0.9693},
    10: {"A2": 0.308, "A3": 0.975, "B3": 0.284, "B4": 1.716, "D3": 0.223, "D4": 1.777, "d2": 3.078, "c4": 0.9727},
    11: {"A2": 0.285, "A3": 0.927, "B3": 0.321, "B4": 1.679, "D3": 0.256, "D4": 1.744, "d2": 3.173, "c4": 0.9754},
    12: {"A2": 0.266, "A3": 0.886, "B3": 0.354, "B4": 1.646, "D3": 0.283, "D4": 1.717, "d2": 3.258, "c4": 0.9776},
    13: {"A2": 0.249, "A3": 0.850, "B3": 0.382, "B4": 1.618, "D3": 0.307, "D4": 1.693, "d2": 3.336, "c4": 0.9794},
    14: {"A2": 0.235, "A3": 0.817, "B3": 0.406, "B4": 1.594, "D3": 0.328, "D4": 1.672, "d2": 3.407, "c4": 0.9810},
    15: {"A2": 0.223, "A3": 0.789, "B3": 0.428, "B4": 1.572, "D3": 0.347, "D4": 1.653, "d2": 3.472, "c4": 0.9823},
    16: {"A2": 0.212, "A3": 0.763, "B3": 0.448, "B4": 1.552, "D3": 0.363, "D4": 1.637, "d2": 3.532, "c4": 0.9835},
    17: {"A2": 0.203, "A3": 0.739, "B3": 0.466, "B4": 1.534, "D3": 0.378, "D4": 1.622, "d2": 3.588, "c4": 0.9845},
    18: {"A2": 0.194, "A3": 0.718, "B3": 0.482, "B4": 1.518, "D3": 0.391, "D4": 1.608, "d2": 3.640, "c4": 0.9854},
    19: {"A2": 0.187, "A3": 0.698, "B3": 0.497, "B4": 1.503, "D3": 0.403, "D4": 1.597, "d2": 3.689, "c4": 0.9862},
    20: {"A2": 0.180, "A3": 0.680, "B3": 0.510, "B4": 1.490, "D3": 0.415, "D4": 1.585, "d2": 3.735, "c4": 0.9869},
    21: {"A2": 0.173, "A3": 0.663, "B3": 0.523, "B4": 1.477, "D3": 0.425, "D4": 1.575, "d2": 3.778, "c4": 0.9876},
    22: {"A2": 0.167, "A3": 0.647, "B3": 0.534, "B4": 1.466, "D3": 0.434, "D4": 1.566, "d2": 3.819, "c4": 0.9882},
    23: {"A2": 0.162, "A3": 0.633, "B3": 0.545, "B4": 1.455, "D3": 0.443, "D4": 1.557, "d2": 3.858, "c4": 0.9887},
    24: {"A2": 0.157, "A3": 0.619, "B3": 0.555, "B4": 1.445, "D3": 0.451, "D4": 1.548, "d2": 3.895, "c4": 0.9892},
    25: {"A2": 0.153, "A3": 0.606, "B3": 0.565, "B4": 1.435, "D3": 0.459, "D4": 1.541, "d2": 3.931, "c4": 0.9896},
}
# fmt: on


def _get_constants(n: int) -> dict:
    """Return Shewhart constants for subgroup size n (must be 2–25)."""
    if n not in _SHEWHART_CONSTANTS:
        raise ValueError(
            f"Subgroup size n={n} out of range; supported n=2..25 (ASTM E2587)"
        )
    return _SHEWHART_CONSTANTS[n]


# ---------------------------------------------------------------------------
# Pure-Python statistics helpers
# ---------------------------------------------------------------------------

def _mean(xs: list) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _stdev_sample(xs: list) -> float:
    """Sample standard deviation (n-1 denominator)."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _normal_cdf(z: float) -> float:
    """Standard normal CDF using math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _split_subgroups(data: list, n: int) -> list:
    """Split flat list into subgroups of size n (drop incomplete tail)."""
    return [data[i: i + n] for i in range(0, len(data) - n + 1, n)]


# ---------------------------------------------------------------------------
# X̄-R chart
# ---------------------------------------------------------------------------

def xbar_r_chart(data: list, n: int, *, ucl_sigma: float = 3.0) -> dict:
    """
    Compute Shewhart X̄-R control chart limits and flag OOC subgroups.

    Parameters
    ----------
    data : list[float]
        Individual observations. Grouped into subgroups of size *n*;
        any trailing incomplete subgroup is discarded.
    n : int
        Subgroup size (2–25).
    ucl_sigma : float
        Number of sigma for control limits (default 3.0).

    Returns
    -------
    dict with:
        n, k (number of subgroups), xbar_bar, r_bar, constants (A2,D3,D4)
        xbar_ucl/lcl, r_ucl/r_lcl
        subgroup_means, subgroup_ranges
        ooc_xbar, ooc_r — lists of (subgroup_index, value) for OOC points
        sigma_xbar_estimated — estimated process σ from R-bar
    """
    constants = _get_constants(n)
    subgroups = _split_subgroups(data, n)
    k = len(subgroups)
    if k == 0:
        return {"ok": False, "reason": "Not enough data for even one subgroup"}

    means = [_mean(sg) for sg in subgroups]
    ranges = [max(sg) - min(sg) for sg in subgroups]

    xbar_bar = _mean(means)
    r_bar = _mean(ranges)

    A2 = constants["A2"]
    D3 = constants["D3"]
    D4 = constants["D4"]
    d2 = constants["d2"]

    # Scale UCL/LCL factor by ucl_sigma / 3.0 (A2 is calibrated for 3σ)
    k_scale = ucl_sigma / 3.0
    xbar_ucl = xbar_bar + k_scale * A2 * r_bar
    xbar_lcl = xbar_bar - k_scale * A2 * r_bar
    r_ucl = D4 * r_bar  # D3/D4 already encode 3σ; scale adjusts multiplicatively
    r_lcl = D3 * r_bar

    # Estimated sigma
    sigma_est = r_bar / d2 if d2 > 0 else 0.0

    ooc_xbar = [
        {"subgroup": i, "value": means[i]}
        for i in range(k)
        if means[i] > xbar_ucl or means[i] < xbar_lcl
    ]
    ooc_r = [
        {"subgroup": i, "value": ranges[i]}
        for i in range(k)
        if ranges[i] > r_ucl or ranges[i] < r_lcl
    ]

    return {
        "ok": True,
        "chart": "xbar-r",
        "n": n,
        "k": k,
        "xbar_bar": xbar_bar,
        "r_bar": r_bar,
        "sigma_xbar_estimated": sigma_est,
        "constants": {"A2": A2, "D3": D3, "D4": D4, "d2": d2},
        "xbar_ucl": xbar_ucl,
        "xbar_lcl": xbar_lcl,
        "xbar_cl": xbar_bar,
        "r_ucl": r_ucl,
        "r_lcl": r_lcl,
        "r_cl": r_bar,
        "subgroup_means": means,
        "subgroup_ranges": ranges,
        "ooc_xbar": ooc_xbar,
        "ooc_r": ooc_r,
    }


# ---------------------------------------------------------------------------
# X̄-S chart
# ---------------------------------------------------------------------------

def xbar_s_chart(data: list, n: int, *, ucl_sigma: float = 3.0) -> dict:
    """
    Compute Shewhart X̄-S control chart limits and flag OOC subgroups.

    Parameters
    ----------
    data : list[float]
        Individual observations.
    n : int
        Subgroup size (2–25).
    ucl_sigma : float
        Number of sigma for control limits (default 3.0).

    Returns
    -------
    dict with xbar_bar, s_bar, A3, B3, B4, UCL/LCL for both charts,
    subgroup means/stdevs, OOC points, and estimated sigma.
    """
    constants = _get_constants(n)
    subgroups = _split_subgroups(data, n)
    k = len(subgroups)
    if k == 0:
        return {"ok": False, "reason": "Not enough data for even one subgroup"}

    means = [_mean(sg) for sg in subgroups]
    stdevs = [_stdev_sample(sg) for sg in subgroups]

    xbar_bar = _mean(means)
    s_bar = _mean(stdevs)

    A3 = constants["A3"]
    B3 = constants["B3"]
    B4 = constants["B4"]
    c4 = constants["c4"]

    k_scale = ucl_sigma / 3.0
    xbar_ucl = xbar_bar + k_scale * A3 * s_bar
    xbar_lcl = xbar_bar - k_scale * A3 * s_bar
    s_ucl = B4 * s_bar
    s_lcl = B3 * s_bar

    sigma_est = s_bar / c4 if c4 > 0 else 0.0

    ooc_xbar = [
        {"subgroup": i, "value": means[i]}
        for i in range(k)
        if means[i] > xbar_ucl or means[i] < xbar_lcl
    ]
    ooc_s = [
        {"subgroup": i, "value": stdevs[i]}
        for i in range(k)
        if stdevs[i] > s_ucl or stdevs[i] < s_lcl
    ]

    return {
        "ok": True,
        "chart": "xbar-s",
        "n": n,
        "k": k,
        "xbar_bar": xbar_bar,
        "s_bar": s_bar,
        "sigma_xbar_estimated": sigma_est,
        "constants": {"A3": A3, "B3": B3, "B4": B4, "c4": c4},
        "xbar_ucl": xbar_ucl,
        "xbar_lcl": xbar_lcl,
        "xbar_cl": xbar_bar,
        "s_ucl": s_ucl,
        "s_lcl": s_lcl,
        "s_cl": s_bar,
        "subgroup_means": means,
        "subgroup_stdevs": stdevs,
        "ooc_xbar": ooc_xbar,
        "ooc_s": ooc_s,
    }


# ---------------------------------------------------------------------------
# CUSUM (tabular)
# ---------------------------------------------------------------------------

def cusum_chart(
    data: list,
    *,
    target: float | None = None,
    k: float = 0.5,
    h: float = 5.0,
    sigma: float | None = None,
    fast_initial_response: bool = False,
) -> dict:
    """
    Tabular CUSUM chart for individual observations.

    Parameters
    ----------
    data : list[float]
        Individual observations.
    target : float | None
        Process target (μ₀). If None, uses the data mean.
    k : float
        Allowance / slack (in sigma units, default 0.5 → detects 1σ shift).
    h : float
        Decision interval (in sigma units, default 5.0).
    sigma : float | None
        Known or estimated process σ. If None, estimated from moving range.
    fast_initial_response : bool
        If True, initialise C_pos = C_neg = h/2 (Lucas & Crosier, 1982).

    Returns
    -------
    dict with:
        target, sigma, k, h (all in original units)
        c_pos, c_neg  — cumulative sums (lists)
        ooc_high, ooc_low — lists of {index, value, cusum}
        arl_theoretical — approximate ARL when process is in-control (~1/p)
    """
    n = len(data)
    if n < 2:
        return {"ok": False, "reason": "Need at least 2 observations for CUSUM"}

    mu0 = target if target is not None else sum(data) / n

    # Estimate sigma from moving range if not provided
    if sigma is None or sigma <= 0:
        mr = [abs(data[i] - data[i - 1]) for i in range(1, n)]
        mr_bar = sum(mr) / len(mr) if mr else 1.0
        sigma = mr_bar / 1.128  # d2 for n=2

    if sigma <= 0:
        return {"ok": False, "reason": "sigma must be > 0"}

    K = k * sigma  # slack in original units
    H = h * sigma  # decision interval in original units

    # Initialise
    init = H / 2.0 if fast_initial_response else 0.0
    c_pos = [0.0] * n
    c_neg = [0.0] * n

    for i, xi in enumerate(data):
        prev_pos = c_pos[i - 1] if i > 0 else init
        prev_neg = c_neg[i - 1] if i > 0 else -init
        c_pos[i] = max(0.0, prev_pos + (xi - mu0) - K)
        c_neg[i] = min(0.0, prev_neg + (xi - mu0) + K)

    ooc_high = [
        {"index": i, "value": data[i], "cusum": c_pos[i]}
        for i in range(n) if c_pos[i] > H
    ]
    ooc_low = [
        {"index": i, "value": data[i], "cusum": c_neg[i]}
        for i in range(n) if c_neg[i] < -H
    ]

    return {
        "ok": True,
        "chart": "cusum",
        "n": n,
        "target": mu0,
        "sigma": sigma,
        "k_sigma": k,
        "h_sigma": h,
        "K": K,
        "H": H,
        "fast_initial_response": fast_initial_response,
        "c_pos": c_pos,
        "c_neg": c_neg,
        "ooc_high": ooc_high,
        "ooc_low": ooc_low,
    }


# ---------------------------------------------------------------------------
# EWMA chart
# ---------------------------------------------------------------------------

def ewma_chart(
    data: list,
    *,
    lam: float = 0.2,
    target: float | None = None,
    sigma: float | None = None,
    L: float = 3.0,
    steady_state: bool = True,
) -> dict:
    """
    EWMA control chart (Hunter, 1986).

    Parameters
    ----------
    data : list[float]
        Individual observations.
    lam : float
        Smoothing parameter λ ∈ (0, 1]. Default 0.2.
        Small λ → more weight on history (detects small shifts).
    target : float | None
        Process target μ₀ (default = data mean).
    sigma : float | None
        Process σ (default = estimated from moving range).
    L : float
        Control limit multiplier (default 3.0 for ±3σ_ewma).
    steady_state : bool
        If True, use steady-state variance σ²·λ/(2-λ) for all points.
        If False, use exact transient variance for each point (more
        conservative at start-up).

    Returns
    -------
    dict with ewma values, UCL/LCL (per-point if not steady_state, else flat),
    and ooc points.
    """
    n = len(data)
    if n < 1:
        return {"ok": False, "reason": "Need at least 1 observation"}

    if not (0 < lam <= 1.0):
        return {"ok": False, "reason": f"lam must be in (0,1], got {lam}"}

    mu0 = target if target is not None else sum(data) / n

    if sigma is None or sigma <= 0:
        if n < 2:
            return {"ok": False, "reason": "Need at least 2 obs or provide sigma"}
        mr = [abs(data[i] - data[i - 1]) for i in range(1, n)]
        mr_bar = sum(mr) / len(mr)
        sigma = mr_bar / 1.128

    if sigma <= 0:
        return {"ok": False, "reason": "sigma must be > 0"}

    # EWMA values
    z = [0.0] * n
    z_prev = mu0
    for i, xi in enumerate(data):
        z[i] = lam * xi + (1.0 - lam) * z_prev
        z_prev = z[i]

    # Steady-state variance: σ²_z = σ² · λ/(2-λ)
    var_ss = (sigma ** 2) * lam / (2.0 - lam)

    if steady_state:
        sigma_z = math.sqrt(var_ss)
        ucl = [mu0 + L * sigma_z] * n
        lcl = [mu0 - L * sigma_z] * n
    else:
        # Exact transient: σ²_z_i = σ² · λ/(2-λ) · (1 - (1-λ)^(2(i+1)))
        sigma_zs = [
            math.sqrt(var_ss * (1.0 - (1.0 - lam) ** (2 * (i + 1))))
            for i in range(n)
        ]
        ucl = [mu0 + L * sz for sz in sigma_zs]
        lcl = [mu0 - L * sz for sz in sigma_zs]

    ooc = [
        {"index": i, "value": data[i], "ewma": z[i], "ucl": ucl[i], "lcl": lcl[i]}
        for i in range(n)
        if z[i] > ucl[i] or z[i] < lcl[i]
    ]

    return {
        "ok": True,
        "chart": "ewma",
        "n": n,
        "lam": lam,
        "L": L,
        "target": mu0,
        "sigma": sigma,
        "steady_state": steady_state,
        "sigma_ewma_ss": math.sqrt(var_ss),
        "ewma": z,
        "ucl": ucl,
        "lcl": lcl,
        "ooc": ooc,
    }


# ---------------------------------------------------------------------------
# Run rules (Nelson 1984 + Western Electric)
# ---------------------------------------------------------------------------

def run_rules(
    data: list,
    *,
    center: float | None = None,
    sigma: float | None = None,
    rules: list | None = None,
) -> dict:
    """
    Detect special causes using Nelson rules 1–8 and Western Electric rules.

    Nelson rules (Nelson, 1984 JQT 16:4):
      1. Any point beyond ±3σ (same as OOC on Shewhart chart)
      2. 9 consecutive points same side of center line
      3. 6 consecutive points strictly increasing or decreasing (trend)
      4. 14 consecutive points alternating up/down
      5. 2 of 3 consecutive points beyond ±2σ (same side)
      6. 4 of 5 consecutive points beyond ±1σ (same side)
      7. 15 consecutive points within ±1σ (hugging)
      8. 8 consecutive points outside ±1σ on both sides

    Western Electric rules (WECO):
      WE1. 1 point beyond ±3σ (same as Nelson 1)
      WE2. 2 of 3 consecutive beyond ±2σ (same side) (same as Nelson 5)
      WE3. 4 of 5 consecutive beyond ±1σ (same side) (same as Nelson 6)
      WE4. 8 consecutive same side of CL (similar to Nelson 2)

    Parameters
    ----------
    data : list[float]
        Individual observations (not subgroup means).
    center : float | None
        Center line. If None, use data mean.
    sigma : float | None
        Process σ. If None, estimated from moving range.
    rules : list | None
        Subset of rules to check, e.g. ["nelson1","nelson2","weco4"].
        If None, all rules are checked.

    Returns
    -------
    dict with:
        center, sigma
        violations — dict mapping rule_name → list of point indices
        any_violation — bool
    """
    n = len(data)
    if n < 1:
        return {"ok": False, "reason": "Need at least 1 observation"}

    mu = center if center is not None else sum(data) / n

    if sigma is None or sigma <= 0:
        if n < 2:
            return {
                "ok": False,
                "reason": "Need at least 2 observations or provide sigma",
            }
        mr = [abs(data[i] - data[i - 1]) for i in range(1, n)]
        mr_bar = sum(mr) / len(mr) if mr else 1.0
        sigma = mr_bar / 1.128

    if sigma <= 0:
        return {"ok": False, "reason": "sigma must be > 0"}

    ALL_RULES = {
        "nelson1", "nelson2", "nelson3", "nelson4",
        "nelson5", "nelson6", "nelson7", "nelson8",
        "weco1", "weco2", "weco3", "weco4",
    }
    active = set(rules) if rules else ALL_RULES

    # Zone boundaries (sigma multiples)
    s1 = sigma
    s2 = 2.0 * sigma
    s3 = 3.0 * sigma

    # Pre-compute per-point zone
    # zone: +3=above+3σ, +2=above+2σ, +1=above+1σ, 0=within±1σ, -1,-2,-3 mirror
    def _zone(x: float) -> int:
        d = x - mu
        if d >= s3: return 3
        if d >= s2: return 2
        if d >= s1: return 1
        if d <= -s3: return -3
        if d <= -s2: return -2
        if d <= -s1: return -1
        return 0

    zones = [_zone(xi) for xi in data]
    # Side: True = above center, False = below center (ignoring points on CL)
    sides = [xi > mu for xi in data]  # True=above, False=at-or-below

    violations: dict = {}

    # -- Nelson 1: beyond ±3σ
    if "nelson1" in active or "weco1" in active:
        pts = [i for i, z in enumerate(zones) if abs(z) == 3]
        if "nelson1" in active:
            violations["nelson1"] = pts
        if "weco1" in active:
            violations["weco1"] = pts

    # -- Nelson 2: 9 consecutive same side of CL (side determined by data vs center)
    if "nelson2" in active:
        run_len = 9
        pts = []
        for i in range(run_len - 1, n):
            window_s = sides[i - run_len + 1: i + 1]
            window_d = data[i - run_len + 1: i + 1]
            if all(window_s) or all(xi < mu for xi in window_d):
                pts.extend(range(i - run_len + 1, i + 1))
        violations["nelson2"] = sorted(set(pts))

    # -- WECO 4: 8 consecutive same side of CL
    if "weco4" in active:
        run_len = 8
        pts = []
        for i in range(run_len - 1, n):
            window_d = data[i - run_len + 1: i + 1]
            if all(xi > mu for xi in window_d) or all(xi < mu for xi in window_d):
                pts.extend(range(i - run_len + 1, i + 1))
        violations["weco4"] = sorted(set(pts))

    # -- Nelson 3: 6 consecutive monotone (strictly increasing or decreasing)
    if "nelson3" in active:
        run_len = 6
        pts = []
        for i in range(run_len - 1, n):
            window = data[i - run_len + 1: i + 1]
            if all(window[j] < window[j + 1] for j in range(run_len - 1)):
                pts.extend(range(i - run_len + 1, i + 1))
            elif all(window[j] > window[j + 1] for j in range(run_len - 1)):
                pts.extend(range(i - run_len + 1, i + 1))
        violations["nelson3"] = sorted(set(pts))

    # -- Nelson 4: 14 consecutive alternating
    if "nelson4" in active:
        run_len = 14
        pts = []
        for i in range(run_len - 1, n):
            window = data[i - run_len + 1: i + 1]
            alt = all(
                (window[j] < window[j + 1]) != (window[j + 1] < window[j + 2])
                for j in range(run_len - 2)
            )
            if alt:
                pts.extend(range(i - run_len + 1, i + 1))
        violations["nelson4"] = sorted(set(pts))

    # -- Nelson 5 / WECO 2: 2 of 3 consecutive beyond ±2σ (same side)
    for rule_name, run_len in [("nelson5", 3), ("weco2", 3)]:
        if rule_name not in active:
            continue
        pts = []
        for i in range(run_len - 1, n):
            window = zones[i - run_len + 1: i + 1]
            above = sum(1 for z in window if z >= 2)
            below = sum(1 for z in window if z <= -2)
            if above >= 2 or below >= 2:
                pts.extend(range(i - run_len + 1, i + 1))
        violations[rule_name] = sorted(set(pts))

    # -- Nelson 6 / WECO 3: 4 of 5 consecutive beyond ±1σ (same side)
    for rule_name, run_len in [("nelson6", 5), ("weco3", 5)]:
        if rule_name not in active:
            continue
        pts = []
        for i in range(run_len - 1, n):
            window = zones[i - run_len + 1: i + 1]
            above = sum(1 for z in window if z >= 1)
            below = sum(1 for z in window if z <= -1)
            if above >= 4 or below >= 4:
                pts.extend(range(i - run_len + 1, i + 1))
        violations[rule_name] = sorted(set(pts))

    # -- Nelson 7: 15 consecutive within ±1σ (hugging center)
    if "nelson7" in active:
        run_len = 15
        pts = []
        for i in range(run_len - 1, n):
            window = zones[i - run_len + 1: i + 1]
            if all(z == 0 for z in window):
                pts.extend(range(i - run_len + 1, i + 1))
        violations["nelson7"] = sorted(set(pts))

    # -- Nelson 8: 8 consecutive outside ±1σ (both sides)
    if "nelson8" in active:
        run_len = 8
        pts = []
        for i in range(run_len - 1, n):
            window = zones[i - run_len + 1: i + 1]
            if all(abs(z) >= 1 for z in window):
                pts.extend(range(i - run_len + 1, i + 1))
        violations["nelson8"] = sorted(set(pts))

    any_violation = any(len(v) > 0 for v in violations.values())

    return {
        "ok": True,
        "chart": "run-rules",
        "n": n,
        "center": mu,
        "sigma": sigma,
        "sigma_1": s1,
        "sigma_2": s2,
        "sigma_3": s3,
        "violations": violations,
        "any_violation": any_violation,
    }
