"""
kerf_cad_core.tolstack.stack — 1D dimensional tolerance stack-up analysis.

Implements four stack-up methods:

  "worst-case"   — Arithmetic / worst-case stack (WC):
                     gap_min = nominal_gap - Σ|tol_i|
                     gap_max = nominal_gap + Σ|tol_i|

  "rss"          — Root-Sum-Square statistical stack (RSS):
                     sigma_i = tol_i / 3   (assumes ±3σ process)
                     sigma_gap = √Σ sigma_i²
                     gap_min/max = nominal ± 3·sigma_gap

  "mrss"         — Modified RSS / Benderized (Bender, SAE 680490):
                     Uses correction factor Cf (default 1.5):
                     gap_tolerance = Cf · √Σ tol_i²
                     Corrects for non-normal / mixed distributions.

  "monte-carlo"  — Monte-Carlo simulation with seeded deterministic LCG.
                   No numpy required.  Default 100 000 samples.
                   Samples each contributor from its declared distribution
                   (normal or uniform).  Reports Cp, Cpk, yield, defect ppm.

Input — contributors:
    Each contributor is a dict with:
      nominal      (float)   — nominal dimension
      plus_tol     (float)   — upper tolerance (must be >= 0)
      minus_tol    (float)   — lower tolerance (magnitude, must be >= 0)
      direction    (int)     — +1 or -1 (sign contribution in the stack)
      distribution (str)     — "normal" (default) or "uniform"
                               normal:  mean = nominal, sigma = tol/3
                               uniform: mean = nominal, half-width = tol

    Asymmetric tolerances are symmetrised:
        tol_symmetric = (plus_tol + minus_tol) / 2
        bias          = (plus_tol - minus_tol) / 2  added to nominal

Output dict (success):
    ok                 : True
    method             : method name
    gap_nominal        : sum of (direction × nominal) for all contributors
    gap_min_wc         : worst-case gap minimum
    gap_max_wc         : worst-case gap maximum
    gap_min            : method gap minimum (±3σ for RSS/MRSS, MC 0.135% for MC)
    gap_max            : method gap maximum
    sigma_gap          : 1σ of gap (None for worst-case)
    cp                 : process capability index (None for worst-case)
    cpk                : process performance index (None for worst-case)
    defect_ppm         : predicted defect PPM outside [gap_min_wc, gap_max_wc]
    yield_pct          : predicted yield % inside [gap_min_wc, gap_max_wc]
    warnings           : list of human-readable warning strings
    contributors_used  : list of contributor dicts as parsed/normalised

Output dict (failure):
    ok                 : False
    reason             : human-readable explanation

Functions NEVER raise.

Units
-----
All dimensions/tolerances in the same unit as the caller supplies.
No unit conversion is performed.

References
----------
Dimensioning and Tolerancing Handbook, McGraw-Hill (Drake, 1999)
Bender, A. SAE Technical Paper 680490, 1968.
Gilson, J. "A New Approach to Engineering Tolerances" — Machinery Pub., 1951.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _guard_direction(value: Any) -> str | None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return f"direction must be +1 or -1, got {value!r}"
    if v not in (1, -1):
        return f"direction must be +1 or -1, got {v}"
    return None


# ---------------------------------------------------------------------------
# Deterministic LCG (no numpy, seeded)
# ---------------------------------------------------------------------------
# Numerical Recipes LCG parameters (Park & Miller variant)
_LCG_A = 1664525
_LCG_C = 1013904223
_LCG_M = 2 ** 32


def _lcg_uniform(seed: int, n: int):
    """Generate *n* uniform [0, 1) samples via LCG.  Returns list[float]."""
    state = seed & (_LCG_M - 1)
    results = []
    for _ in range(n):
        state = (_LCG_A * state + _LCG_C) & (_LCG_M - 1)
        results.append(state / _LCG_M)
    return results


def _box_muller(u1: float, u2: float) -> tuple[float, float]:
    """Box-Muller transform: two U(0,1) → two N(0,1)."""
    # Guard against exact 0
    if u1 < 1e-15:
        u1 = 1e-15
    if u2 < 1e-15:
        u2 = 1e-15
    r = math.sqrt(-2.0 * math.log(u1))
    theta = 2.0 * math.pi * u2
    return r * math.cos(theta), r * math.sin(theta)


def _normal_samples(seed: int, n: int) -> list[float]:
    """Generate *n* N(0,1) samples from seed, using Box-Muller."""
    # Need n uniform pairs
    needed = n + (n % 2)  # even
    uniforms = _lcg_uniform(seed, needed)
    normals = []
    for i in range(0, needed, 2):
        z0, z1 = _box_muller(uniforms[i], uniforms[i + 1])
        normals.append(z0)
        normals.append(z1)
    return normals[:n]


# ---------------------------------------------------------------------------
# erf approximation (Abramowitz & Stegun 7.1.26 — max error < 1.5e-7)
# No math.erf needed (it's in Python's math since 3.2), but we use math.erf.
# ---------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    """CDF of N(0,1) at x."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Contributor parsing
# ---------------------------------------------------------------------------

_VALID_DISTRIBUTIONS = {"normal", "uniform"}


def _parse_contributors(
    raw_contributors: list[Any],
    warnings: list[str],
) -> list[dict] | None:
    """
    Parse and normalise contributor list.

    Returns list of normalised contributor dicts on success, or None on fatal
    error (a warning is appended for each non-fatal issue).

    Each returned dict has:
        nominal_adj   — adjusted nominal (symmetrised: original + bias)
        tol           — symmetric tolerance half-width
        direction     — +1 or -1
        distribution  — "normal" or "uniform"
        original      — copy of original input dict
    """
    if not isinstance(raw_contributors, list):
        return None

    parsed = []
    for idx, c in enumerate(raw_contributors):
        label = f"contributor[{idx}]"
        if not isinstance(c, dict):
            warnings.append(f"{label}: must be a dict, skipping")
            continue

        # nominal
        try:
            nominal = float(c.get("nominal", 0.0))
        except (TypeError, ValueError):
            warnings.append(f"{label}: invalid nominal {c.get('nominal')!r}, using 0.0")
            nominal = 0.0

        # plus_tol
        plus_tol_raw = c.get("plus_tol", 0.0)
        err = _guard_nonneg("plus_tol", plus_tol_raw)
        if err:
            warnings.append(f"{label}: {err}, using 0.0")
            plus_tol = 0.0
        else:
            plus_tol = float(plus_tol_raw)

        # minus_tol
        minus_tol_raw = c.get("minus_tol", 0.0)
        err = _guard_nonneg("minus_tol", minus_tol_raw)
        if err:
            warnings.append(f"{label}: {err}, using 0.0")
            minus_tol = 0.0
        else:
            minus_tol = float(minus_tol_raw)

        # direction
        dir_raw = c.get("direction", 1)
        err = _guard_direction(dir_raw)
        if err:
            warnings.append(f"{label}: {err}, using +1")
            direction = 1
        else:
            direction = int(dir_raw)

        # distribution
        dist_raw = str(c.get("distribution", "normal")).strip().lower()
        if dist_raw not in _VALID_DISTRIBUTIONS:
            warnings.append(
                f"{label}: unknown distribution {c.get('distribution')!r}, using 'normal'"
            )
            dist_raw = "normal"

        # Symmetrise asymmetric tolerances
        tol_sym = (plus_tol + minus_tol) / 2.0
        bias = (plus_tol - minus_tol) / 2.0  # centre shift

        if plus_tol == 0.0 and minus_tol == 0.0:
            warnings.append(
                f"{label}: both plus_tol and minus_tol are 0 — zero-tolerance contributor"
            )

        if abs(plus_tol - minus_tol) > 1e-12 * max(1.0, plus_tol + minus_tol):
            warnings.append(
                f"{label}: asymmetric tolerance "
                f"(+{plus_tol}/−{minus_tol}); symmetrised to ±{tol_sym:.6g} "
                f"with nominal shift {bias:+.6g}"
            )

        parsed.append({
            "nominal_adj": nominal + bias,
            "tol": tol_sym,
            "direction": direction,
            "distribution": dist_raw,
            "original": dict(c),
        })

    return parsed


# ---------------------------------------------------------------------------
# Core stack-up methods
# ---------------------------------------------------------------------------

def _wc_gap(parsed: list[dict]) -> tuple[float, float, float]:
    """Return (gap_nominal, gap_min, gap_max) for worst-case arithmetic stack."""
    gap_nom = sum(p["direction"] * p["nominal_adj"] for p in parsed)
    total_tol = sum(p["tol"] for p in parsed)
    return gap_nom, gap_nom - total_tol, gap_nom + total_tol


def _rss_analysis(parsed: list[dict]) -> dict:
    """RSS (root-sum-square) statistical stack."""
    gap_nom, gap_min_wc, gap_max_wc = _wc_gap(parsed)

    # Each tol is ±tol at ±3σ → σ_i = tol_i / 3
    var_sum = sum((p["tol"] / 3.0) ** 2 for p in parsed)
    sigma_gap = math.sqrt(var_sum)

    # ±3σ limits
    gap_min = gap_nom - 3.0 * sigma_gap
    gap_max = gap_nom + 3.0 * sigma_gap

    # Cp / Cpk relative to WC spec limits
    spec_range = gap_max_wc - gap_min_wc
    cp = spec_range / (6.0 * sigma_gap) if sigma_gap > 0 else float("inf")

    # For centred process: cpk == cp
    dist_to_upper = (gap_max_wc - gap_nom) / (3.0 * sigma_gap) if sigma_gap > 0 else float("inf")
    dist_to_lower = (gap_nom - gap_min_wc) / (3.0 * sigma_gap) if sigma_gap > 0 else float("inf")
    cpk = min(dist_to_upper, dist_to_lower) / 1.0  # = min(USL - mu, mu - LSL) / 3σ

    # ppm defect: fraction outside [gap_min_wc, gap_max_wc]
    if sigma_gap > 0:
        z_upper = (gap_max_wc - gap_nom) / sigma_gap
        z_lower = (gap_nom - gap_min_wc) / sigma_gap
        p_inside = _normal_cdf(z_upper) - _normal_cdf(-z_lower)
    else:
        p_inside = 1.0

    defect_ppm = (1.0 - p_inside) * 1e6
    yield_pct = p_inside * 100.0

    return {
        "ok": True,
        "method": "rss",
        "gap_nominal": gap_nom,
        "gap_min_wc": gap_min_wc,
        "gap_max_wc": gap_max_wc,
        "gap_min": gap_min,
        "gap_max": gap_max,
        "sigma_gap": sigma_gap,
        "cp": cp,
        "cpk": cpk,
        "defect_ppm": defect_ppm,
        "yield_pct": yield_pct,
    }


def _mrss_analysis(parsed: list[dict], cf: float = 1.5) -> dict:
    """Modified RSS / Benderized stack (Bender, SAE 680490)."""
    gap_nom, gap_min_wc, gap_max_wc = _wc_gap(parsed)

    # Bender correction: gap_tol = Cf × √Σ tol_i²
    sum_sq = sum(p["tol"] ** 2 for p in parsed)
    gap_tol = cf * math.sqrt(sum_sq)

    gap_min = gap_nom - gap_tol
    gap_max = gap_nom + gap_tol

    # sigma implied by Cf-scaled tolerance (treat ± gap_tol as ±3σ)
    sigma_gap = gap_tol / 3.0

    spec_range = gap_max_wc - gap_min_wc
    cp = spec_range / (6.0 * sigma_gap) if sigma_gap > 0 else float("inf")

    dist_to_upper = (gap_max_wc - gap_nom) / (3.0 * sigma_gap) if sigma_gap > 0 else float("inf")
    dist_to_lower = (gap_nom - gap_min_wc) / (3.0 * sigma_gap) if sigma_gap > 0 else float("inf")
    cpk = min(dist_to_upper, dist_to_lower)

    if sigma_gap > 0:
        z_upper = (gap_max_wc - gap_nom) / sigma_gap
        z_lower = (gap_nom - gap_min_wc) / sigma_gap
        p_inside = _normal_cdf(z_upper) - _normal_cdf(-z_lower)
    else:
        p_inside = 1.0

    defect_ppm = (1.0 - p_inside) * 1e6
    yield_pct = p_inside * 100.0

    return {
        "ok": True,
        "method": "mrss",
        "gap_nominal": gap_nom,
        "gap_min_wc": gap_min_wc,
        "gap_max_wc": gap_max_wc,
        "gap_min": gap_min,
        "gap_max": gap_max,
        "sigma_gap": sigma_gap,
        "cp": cp,
        "cpk": cpk,
        "defect_ppm": defect_ppm,
        "yield_pct": yield_pct,
        "bender_cf": cf,
    }


def _mc_analysis(
    parsed: list[dict],
    n_samples: int = 100_000,
    seed: int = 42,
) -> dict:
    """Monte-Carlo stack-up (deterministic LCG, no numpy)."""
    gap_nom, gap_min_wc, gap_max_wc = _wc_gap(parsed)
    n_contrib = len(parsed)

    # Compute the exact number of uniform variates needed: normal contributors
    # require 2·n_samples (Box-Muller pairs), uniform contributors require
    # n_samples.  Pre-size the buffer exactly to avoid IndexError when uniform
    # and normal contributors are mixed in the same stack.
    n_uniforms_needed = sum(
        n_samples * 2 if p["distribution"] == "normal" else n_samples
        for p in parsed
    )
    all_uniform = _lcg_uniform(seed, max(n_uniforms_needed, 1))

    # Reconstruct per-contributor sample arrays
    gap_samples = [0.0] * n_samples

    offset = 0
    for p in parsed:
        mu = p["nominal_adj"]
        tol = p["tol"]
        direction = p["direction"]
        dist = p["distribution"]

        if dist == "normal":
            sigma = tol / 3.0
            # Box-Muller on pairs
            u_block = all_uniform[offset: offset + n_samples * 2]
            offset += n_samples * 2
            for i in range(n_samples):
                u1 = u_block[2 * i]
                u2 = u_block[2 * i + 1]
                if u1 < 1e-15:
                    u1 = 1e-15
                r = math.sqrt(-2.0 * math.log(u1))
                theta = 2.0 * math.pi * u2
                z = r * math.cos(theta)
                sample = mu + sigma * z
                gap_samples[i] += direction * sample
        else:
            # Uniform: mean = mu, half-width = tol
            u_block = all_uniform[offset: offset + n_samples]
            offset += n_samples
            for i in range(n_samples):
                sample = mu + tol * (2.0 * u_block[i] - 1.0)
                gap_samples[i] += direction * sample

    # Compute statistics from gap_samples
    mean_gap = sum(gap_samples) / n_samples
    var = sum((x - mean_gap) ** 2 for x in gap_samples) / (n_samples - 1) if n_samples > 1 else 0.0
    sigma_gap = math.sqrt(var)

    gap_min_mc = min(gap_samples)
    gap_max_mc = max(gap_samples)

    # Count defects (outside WC spec)
    n_defect = sum(1 for g in gap_samples if g < gap_min_wc or g > gap_max_wc)
    defect_ppm = n_defect / n_samples * 1e6
    yield_pct = (1.0 - n_defect / n_samples) * 100.0

    # Cp / Cpk
    spec_range = gap_max_wc - gap_min_wc
    cp = spec_range / (6.0 * sigma_gap) if sigma_gap > 0 else float("inf")
    if sigma_gap > 0:
        cpk = min(gap_max_wc - mean_gap, mean_gap - gap_min_wc) / (3.0 * sigma_gap)
    else:
        cpk = float("inf")

    # Reported ±3σ (or percentile-equivalent) gap limits
    gap_min_stat = mean_gap - 3.0 * sigma_gap
    gap_max_stat = mean_gap + 3.0 * sigma_gap

    return {
        "ok": True,
        "method": "monte-carlo",
        "gap_nominal": gap_nom,
        "gap_min_wc": gap_min_wc,
        "gap_max_wc": gap_max_wc,
        "gap_min": gap_min_stat,
        "gap_max": gap_max_stat,
        "gap_min_mc_observed": gap_min_mc,
        "gap_max_mc_observed": gap_max_mc,
        "sigma_gap": sigma_gap,
        "mean_gap": mean_gap,
        "cp": cp,
        "cpk": cpk,
        "defect_ppm": defect_ppm,
        "yield_pct": yield_pct,
        "n_samples": n_samples,
        "seed": seed,
    }


def _wc_only_result(parsed: list[dict]) -> dict:
    """Worst-case arithmetic stack result."""
    gap_nom, gap_min, gap_max = _wc_gap(parsed)
    return {
        "ok": True,
        "method": "worst-case",
        "gap_nominal": gap_nom,
        "gap_min_wc": gap_min,
        "gap_max_wc": gap_max,
        "gap_min": gap_min,
        "gap_max": gap_max,
        "sigma_gap": None,
        "cp": None,
        "cpk": None,
        "defect_ppm": None,
        "yield_pct": None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_VALID_METHODS = {"worst-case", "rss", "mrss", "monte-carlo"}


def analyze_stack(
    contributors: list[dict],
    *,
    method: str = "rss",
    n_samples: int = 100_000,
    seed: int = 42,
    bender_cf: float = 1.5,
) -> dict:
    """
    Perform 1D dimensional tolerance stack-up analysis.

    Parameters
    ----------
    contributors : list[dict]
        List of contributor dicts.  Each may contain:
          nominal      (float, default 0.0)   — nominal dimension
          plus_tol     (float, default 0.0)   — upper tolerance magnitude >= 0
          minus_tol    (float, default 0.0)   — lower tolerance magnitude >= 0
          direction    (int,   default +1)    — +1 or -1
          distribution (str,   default "normal") — "normal" or "uniform"

    method : str
        Analysis method:
          "worst-case"  — arithmetic / worst-case (WC)
          "rss"         — root-sum-square statistical (default)
          "mrss"        — modified RSS / Benderized
          "monte-carlo" — Monte-Carlo simulation (seeded, deterministic)

    n_samples : int
        Number of Monte-Carlo samples (only used for method="monte-carlo").
        Default 100 000.  Must be >= 2.

    seed : int
        LCG seed for Monte-Carlo reproducibility (default 42).

    bender_cf : float
        Bender correction factor for MRSS (default 1.5).  Must be > 0.

    Returns
    -------
    dict
        On success: ok=True + analysis fields (see module docstring).
        On failure: ok=False + reason string.
        Always includes a "warnings" list (may be empty).
        Always includes a "contributors_used" list.
        Never raises.
    """
    warnings: list[str] = []

    # Validate method
    method_clean = str(method).strip().lower()
    if method_clean not in _VALID_METHODS:
        return _err(
            f"Unknown method {method!r}. Supported: {sorted(_VALID_METHODS)}"
        )

    # Validate n_samples
    try:
        n_samples_int = int(n_samples)
    except (TypeError, ValueError):
        return _err(f"n_samples must be an integer, got {n_samples!r}")
    if n_samples_int < 2:
        return _err(f"n_samples must be >= 2, got {n_samples_int}")

    # Validate bender_cf
    try:
        cf = float(bender_cf)
    except (TypeError, ValueError):
        return _err(f"bender_cf must be a number, got {bender_cf!r}")
    if not math.isfinite(cf) or cf <= 0:
        return _err(f"bender_cf must be > 0, got {cf}")

    # Validate seed
    try:
        seed_int = int(seed)
    except (TypeError, ValueError):
        return _err(f"seed must be an integer, got {seed!r}")

    # Parse contributors
    if not isinstance(contributors, list):
        return _err("contributors must be a list")

    if len(contributors) == 0:
        warnings.append("contributors list is empty; gap = 0 with no uncertainty")

    parsed = _parse_contributors(contributors, warnings)
    if parsed is None:
        return _err("contributors must be a list of dicts")

    # Build contributors_used from parsed entries
    contributors_used = [
        {
            "nominal": p["nominal_adj"],
            "tol": p["tol"],
            "direction": p["direction"],
            "distribution": p["distribution"],
        }
        for p in parsed
    ]

    # Run selected method
    if method_clean == "worst-case":
        result = _wc_only_result(parsed)
    elif method_clean == "rss":
        result = _rss_analysis(parsed)
    elif method_clean == "mrss":
        result = _mrss_analysis(parsed, cf=cf)
    else:  # monte-carlo
        result = _mc_analysis(parsed, n_samples=n_samples_int, seed=seed_int)

    result["warnings"] = warnings
    result["contributors_used"] = contributors_used

    return result
