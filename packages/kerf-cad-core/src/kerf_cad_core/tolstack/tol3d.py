"""
kerf_cad_core.tolstack.tol3d — 3D vector-loop tolerance stack-up analysis.

Models a spatial dimension chain as a series of 6-DOF contributors
(Δx, Δy, Δz, Δrx, Δry, Δrz) each with a tolerance distribution.

Methods
-------
  worst_case   — arithmetic sum of absolute tolerance magnitudes per axis
  rss          — root-sum-square (normal, σ = tol/3)
  monte_carlo  — seeded deterministic LCG (no numpy), Box-Muller normals

Jacobian
--------
  Computed via central finite difference on the closure vector
  (final accumulated pose) with respect to each contributor's mean value.

Output
------
  Closure vector (6 components), worst-case, RSS, and MC uncertainty
  bands per axis, total position deviation (3D), total orientation
  deviation (3D), and flagged out-of-range axes.

Pure Python — no numpy, no OCC.

References
----------
Wittwer, J.W. (2004). "Monte Carlo Simulation Basics."
Chase, K.W. & Parkinson, A.R. (1991). "A survey of research in the
    application of tolerance analysis to the design of mechanical
    assemblies." Research in Engineering Design, 3, 23-37.
Tolerance analysis of 3D assemblies, Garrett & Hall, ADCATS Report 97-4.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

_N_AXES = 6  # (x, y, z, rx, ry, rz)
_AXIS_NAMES = ("x", "y", "z", "rx", "ry", "rz")

# LCG parameters (Numerical Recipes, Park & Miller variant)
_LCG_A = 1_664_525
_LCG_C = 1_013_904_223
_LCG_M = 2 ** 32

_VALID_DISTRIBUTIONS = {"normal", "uniform"}

_FD_STEP = 1e-7  # finite-difference step for Jacobian


# ---------------------------------------------------------------------------
# Pure-Python maths helpers
# ---------------------------------------------------------------------------

def _lcg_uniform(seed: int, n: int) -> list:
    """Generate *n* U[0,1) samples via LCG."""
    state = seed & (_LCG_M - 1)
    out = []
    for _ in range(n):
        state = (_LCG_A * state + _LCG_C) & (_LCG_M - 1)
        out.append(state / _LCG_M)
    return out


def _box_muller(u1: float, u2: float):
    """Two U(0,1) → two N(0,1) via Box-Muller."""
    u1 = max(u1, 1e-15)
    u2 = max(u2, 1e-15)
    r = math.sqrt(-2.0 * math.log(u1))
    th = 2.0 * math.pi * u2
    return r * math.cos(th), r * math.sin(th)


def _normal_samples(seed: int, n: int) -> list:
    """Generate *n* N(0,1) samples from *seed*."""
    needed = n + (n % 2)
    u = _lcg_uniform(seed, needed)
    out = []
    for i in range(0, needed, 2):
        z0, z1 = _box_muller(u[i], u[i + 1])
        out.extend([z0, z1])
    return out[:n]


def _vec_add(a: list, b: list) -> list:
    return [a[i] + b[i] for i in range(_N_AXES)]


def _vec_scale(v: list, s: float) -> list:
    return [x * s for x in v]


def _norm3(v: list) -> float:
    """Euclidean norm of first 3 components."""
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _norm_rot(v: list) -> float:
    """Euclidean norm of last 3 (rotation) components."""
    return math.sqrt(v[3] ** 2 + v[4] ** 2 + v[5] ** 2)


# ---------------------------------------------------------------------------
# Closure function
# ---------------------------------------------------------------------------

def _closure(contributors: list) -> list:
    """
    Sum contributor mean vectors to produce the 6-DOF closure vector.

    For linear chains the closure is simply:
        C_k = Σ_i  direction_i · mean_k_i   for k in {x, y, z, rx, ry, rz}

    Returns list of 6 floats.
    """
    result = [0.0] * _N_AXES
    for c in contributors:
        d = c["direction"]
        mean = c["mean"]
        for k in range(_N_AXES):
            result[k] += d * mean[k]
    return result


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------

def _parse_contributor(idx: int, raw: Any, warnings: list) -> dict | None:
    """
    Parse a single contributor dict.

    Expected keys (all optional, default 0.0):
        mean      — list[6] of floats [x, y, z, rx, ry, rz] (nominal values)
        tol       — list[6] of floats (symmetric tolerance half-widths >= 0)
                    OR a single float applied to all 6 axes
        direction — int, +1 or -1 (default +1)
        distribution — "normal" or "uniform" (default "normal")
        label     — optional string name
    """
    label = f"contributor[{idx}]"

    if not isinstance(raw, dict):
        warnings.append(f"{label}: must be a dict, skipping")
        return None

    # mean
    raw_mean = raw.get("mean", [0.0] * _N_AXES)
    try:
        if isinstance(raw_mean, (int, float)):
            mean = [float(raw_mean)] * _N_AXES
        else:
            mean = [float(v) for v in raw_mean]
        if len(mean) != _N_AXES:
            warnings.append(
                f"{label}: mean must have 6 elements, got {len(mean)}; padding with 0"
            )
            mean = (mean + [0.0] * _N_AXES)[:_N_AXES]
    except (TypeError, ValueError) as e:
        warnings.append(f"{label}: invalid mean {raw_mean!r} ({e}), using zeros")
        mean = [0.0] * _N_AXES

    # tol
    raw_tol = raw.get("tol", 0.0)
    try:
        if isinstance(raw_tol, (int, float)):
            tol = [float(raw_tol)] * _N_AXES
        else:
            tol = [float(v) for v in raw_tol]
        if len(tol) != _N_AXES:
            warnings.append(
                f"{label}: tol must have 6 elements, got {len(tol)}; padding with 0"
            )
            tol = (tol + [0.0] * _N_AXES)[:_N_AXES]
    except (TypeError, ValueError) as e:
        warnings.append(f"{label}: invalid tol {raw_tol!r} ({e}), using zeros")
        tol = [0.0] * _N_AXES

    for k, t in enumerate(tol):
        if not math.isfinite(t) or t < 0:
            warnings.append(
                f"{label}: tol[{_AXIS_NAMES[k]}]={t!r} must be finite >= 0; clamped to 0"
            )
            tol[k] = 0.0

    # direction
    raw_dir = raw.get("direction", 1)
    try:
        direction = int(raw_dir)
        if direction not in (1, -1):
            warnings.append(f"{label}: direction must be +1 or -1, got {raw_dir!r}; using +1")
            direction = 1
    except (TypeError, ValueError):
        warnings.append(f"{label}: direction must be +1 or -1, got {raw_dir!r}; using +1")
        direction = 1

    # distribution
    dist = str(raw.get("distribution", "normal")).strip().lower()
    if dist not in _VALID_DISTRIBUTIONS:
        warnings.append(f"{label}: unknown distribution {raw.get('distribution')!r}; using 'normal'")
        dist = "normal"

    if all(t == 0.0 for t in tol):
        warnings.append(f"{label}: all tolerances are zero — zero-tol contributor")

    return {
        "mean": mean,
        "tol": tol,
        "direction": direction,
        "distribution": dist,
        "label": str(raw.get("label", label)),
    }


# ---------------------------------------------------------------------------
# Jacobian (finite difference, central)
# ---------------------------------------------------------------------------

def _compute_jacobian(contributors: list) -> list:
    """
    Compute sensitivity Jacobian J[output_axis][contributor_idx][mean_axis].

    J[j][i][k] = ∂ C_j / ∂ mean_k_i

    For linear vector summation this is simply direction_i * I_jk, but we
    compute it numerically via central finite difference so that non-linear
    extensions (e.g. rotation composition) are handled automatically.

    Returns: J as list[6][n][6] of floats.
    """
    n = len(contributors)
    # Allocate J[out_axis][contributor_idx][in_axis]
    J = [[[0.0] * _N_AXES for _ in range(n)] for _ in range(_N_AXES)]

    for i, c in enumerate(contributors):
        for k in range(_N_AXES):
            # Perturb contributor i, mean axis k forward and back
            c_fwd = {**c, "mean": list(c["mean"])}
            c_fwd["mean"] = list(c["mean"])
            c_fwd["mean"][k] += _FD_STEP

            c_bwd = {**c, "mean": list(c["mean"])}
            c_bwd["mean"] = list(c["mean"])
            c_bwd["mean"][k] -= _FD_STEP

            contribs_fwd = [contributors[j] if j != i else c_fwd for j in range(n)]
            contribs_bwd = [contributors[j] if j != i else c_bwd for j in range(n)]

            cl_fwd = _closure(contribs_fwd)
            cl_bwd = _closure(contribs_bwd)

            for j in range(_N_AXES):
                J[j][i][k] = (cl_fwd[j] - cl_bwd[j]) / (2.0 * _FD_STEP)

    return J


# ---------------------------------------------------------------------------
# Worst-case analysis
# ---------------------------------------------------------------------------

def _wc_analysis(contributors: list, closure: list) -> dict:
    """
    Worst-case (arithmetic) uncertainty per axis.

    For axis j:  delta_wc_j = Σ_i |J[j][i][k]| · tol_k_i  for each k
    """
    n = len(contributors)
    J = _compute_jacobian(contributors)

    delta = [0.0] * _N_AXES
    for j in range(_N_AXES):
        for i in range(n):
            for k in range(_N_AXES):
                delta[j] += abs(J[j][i][k]) * contributors[i]["tol"][k]

    return {
        "method": "worst-case",
        "closure": closure,
        "delta_per_axis": delta,
        "closure_min": [closure[j] - delta[j] for j in range(_N_AXES)],
        "closure_max": [closure[j] + delta[j] for j in range(_N_AXES)],
        "total_position_deviation": _norm3(delta),
        "total_orientation_deviation": _norm_rot(delta),
    }


# ---------------------------------------------------------------------------
# RSS analysis
# ---------------------------------------------------------------------------

def _rss_analysis(contributors: list, closure: list) -> dict:
    """
    RSS (root-sum-square) uncertainty per axis.

    Assumes tol_k_i = 3σ_k_i (normal distribution).
    sigma_j = √ Σ_i Σ_k (J[j][i][k] · σ_k_i)²
    """
    n = len(contributors)
    J = _compute_jacobian(contributors)

    sigma = [0.0] * _N_AXES
    for j in range(_N_AXES):
        var = 0.0
        for i in range(n):
            for k in range(_N_AXES):
                sigma_ki = contributors[i]["tol"][k] / 3.0
                var += (J[j][i][k] * sigma_ki) ** 2
        sigma[j] = math.sqrt(var)

    delta = [3.0 * s for s in sigma]

    return {
        "method": "rss",
        "closure": closure,
        "sigma_per_axis": sigma,
        "delta_per_axis": delta,
        "closure_min": [closure[j] - delta[j] for j in range(_N_AXES)],
        "closure_max": [closure[j] + delta[j] for j in range(_N_AXES)],
        "total_position_deviation": _norm3(delta),
        "total_orientation_deviation": _norm_rot(delta),
    }


# ---------------------------------------------------------------------------
# Monte-Carlo analysis
# ---------------------------------------------------------------------------

def _mc_analysis(
    contributors: list,
    closure: list,
    n_samples: int = 50_000,
    seed: int = 42,
) -> dict:
    """
    Monte-Carlo 3D tolerance stack-up (seeded LCG, no numpy).

    Samples each contributor's 6-DOF mean from its tolerance distribution
    and accumulates the closure vector.
    """
    n = len(contributors)
    # We need n * 6 samples per contributor axis.
    # For normal: 2 uniforms per sample (Box-Muller); for uniform: 1 per sample.
    # Pre-generate a big block per contributor.

    # samples_per_axis[i][k] = list of n_samples values for contributor i, axis k
    contrib_samples: list = []
    rng_seed = seed

    for i, c in enumerate(contributors):
        dist = c["distribution"]
        axis_samples = []
        for k in range(_N_AXES):
            mu = c["mean"][k]
            tol = c["tol"][k]
            if dist == "normal":
                sigma = tol / 3.0
                z = _normal_samples(rng_seed, n_samples)
                rng_seed = (rng_seed + 1) & 0xFFFFFFFF
                s = [mu + sigma * zi for zi in z]
            else:  # uniform
                u = _lcg_uniform(rng_seed, n_samples)
                rng_seed = (rng_seed + 1) & 0xFFFFFFFF
                s = [mu + tol * (2.0 * ui - 1.0) for ui in u]
            axis_samples.append(s)
        contrib_samples.append(axis_samples)

    # Accumulate closure samples
    closure_samples = [[0.0] * n_samples for _ in range(_N_AXES)]
    for i, c in enumerate(contributors):
        d = c["direction"]
        for k in range(_N_AXES):
            for s in range(n_samples):
                closure_samples[k][s] += d * contrib_samples[i][k][s]

    # Statistics per axis
    mean_cl = [sum(closure_samples[j]) / n_samples for j in range(_N_AXES)]
    var_cl = [
        sum((closure_samples[j][s] - mean_cl[j]) ** 2 for s in range(n_samples))
        / max(n_samples - 1, 1)
        for j in range(_N_AXES)
    ]
    sigma_cl = [math.sqrt(v) for v in var_cl]
    delta = [3.0 * s for s in sigma_cl]

    # Total deviations (using delta as ±3σ per axis)
    pos_dev = _norm3(delta)
    rot_dev = _norm_rot(delta)

    return {
        "method": "monte-carlo",
        "n_samples": n_samples,
        "seed": seed,
        "closure": closure,
        "mean_per_axis": mean_cl,
        "sigma_per_axis": sigma_cl,
        "delta_per_axis": delta,
        "closure_min": [mean_cl[j] - delta[j] for j in range(_N_AXES)],
        "closure_max": [mean_cl[j] + delta[j] for j in range(_N_AXES)],
        "total_position_deviation": pos_dev,
        "total_orientation_deviation": rot_dev,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_VALID_METHODS = {"worst-case", "rss", "monte-carlo"}


def analyze_stack_3d(
    contributors: list,
    *,
    method: str = "rss",
    n_samples: int = 50_000,
    seed: int = 42,
) -> dict:
    """
    Perform 3D vector-loop tolerance stack-up analysis.

    Parameters
    ----------
    contributors : list[dict]
        Each contributor dict:
            mean         list[6] or float — nominal [x,y,z,rx,ry,rz] (default 0)
            tol          list[6] or float — symmetric tol half-widths >= 0 (default 0)
            direction    int (+1 or -1, default +1)
            distribution "normal" or "uniform" (default "normal")
            label        str (optional, for reporting)

    method : str
        "worst-case", "rss" (default), or "monte-carlo"

    n_samples : int
        Monte-Carlo sample count (default 50 000). Min 2.

    seed : int
        LCG seed for Monte-Carlo (default 42).

    Returns
    -------
    dict
        ok: True on success, False on failure.
        On success:
            closure           list[6] — nominal closure vector
            delta_per_axis    list[6] — ±uncertainty per axis (3σ or WC)
            closure_min/max   list[6] — bounds per axis
            total_position_deviation     float — ||delta[:3]||
            total_orientation_deviation  float — ||delta[3:]||
            jacobian          list[6][n][6] — sensitivity matrix (rss/wc only)
            contributors_used list of parsed contributor dicts
            warnings          list[str]
        Never raises.
    """
    warnings: list = []

    # Validate method
    method_clean = str(method).strip().lower()
    if method_clean not in _VALID_METHODS:
        return {
            "ok": False,
            "reason": f"Unknown method {method!r}. Supported: {sorted(_VALID_METHODS)}",
        }

    # Validate n_samples
    try:
        n_samples_int = int(n_samples)
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"n_samples must be an integer, got {n_samples!r}"}
    if n_samples_int < 2:
        return {"ok": False, "reason": f"n_samples must be >= 2, got {n_samples_int}"}

    # Validate seed
    try:
        seed_int = int(seed)
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"seed must be an integer, got {seed!r}"}

    # Parse contributors
    if not isinstance(contributors, list):
        return {"ok": False, "reason": "contributors must be a list"}

    if len(contributors) == 0:
        warnings.append("contributors list is empty — zero closure with no uncertainty")

    parsed = []
    for idx, raw in enumerate(contributors):
        p = _parse_contributor(idx, raw, warnings)
        if p is not None:
            parsed.append(p)

    # Nominal closure
    closure = _closure(parsed) if parsed else [0.0] * _N_AXES

    # Run selected method
    if method_clean == "worst-case":
        result = _wc_analysis(parsed, closure)
    elif method_clean == "rss":
        result = _rss_analysis(parsed, closure)
    else:  # monte-carlo
        result = _mc_analysis(parsed, closure, n_samples=n_samples_int, seed=seed_int)

    # Attach Jacobian for wc/rss (computed during analysis above; re-expose)
    if method_clean in ("worst-case", "rss"):
        result["jacobian"] = _compute_jacobian(parsed) if parsed else []

    result["ok"] = True
    result["warnings"] = warnings
    result["contributors_used"] = [
        {
            "label": p["label"],
            "mean": p["mean"],
            "tol": p["tol"],
            "direction": p["direction"],
            "distribution": p["distribution"],
        }
        for p in parsed
    ]
    result["axis_names"] = list(_AXIS_NAMES)

    return result
