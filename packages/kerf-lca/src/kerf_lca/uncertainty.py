"""
Uncertainty analysis for LCA — ISO 14044 §4.3.3, §4.5.

Implements:
  - Lognormal uncertainty bounds per characterisation factor
  - Monte Carlo uncertainty propagation
  - Returns mean + 90 % confidence interval

Background:
  LCA characterisation factors are typically represented as lognormal
  distributions.  The geometric standard deviation (GSD²) is used in
  pedigree-matrix uncertainty analysis (Weidema et al., 2013).

  This module keeps scipy optional — if unavailable, a pure-NumPy
  fallback is used.
"""

from __future__ import annotations

import math
import statistics
from typing import Callable, Any

# ---------------------------------------------------------------------------
# Per-category geometric standard deviations (GSD²)
# Source: Ecoinvent pedigree matrix defaults; Huijbregts et al. 2001
# σ_g = sqrt(GSD²)  →  σ_ln = ln(σ_g)
# ---------------------------------------------------------------------------

_GSD2_DEFAULTS: dict[str, float] = {
    "gwp100": 1.05,   # very well characterised
    "ap": 1.20,
    "ep": 1.25,
    "htp": 2.00,      # high uncertainty for toxicity
    "water": 1.50,
    "pm25": 1.30,
}

# Default for unknown categories
_GSD2_FALLBACK = 1.50


def gsd2_for_category(category: str) -> float:
    """Return GSD² (geometric standard deviation squared) for an impact category."""
    return _GSD2_DEFAULTS.get(category, _GSD2_FALLBACK)


def lognormal_params(mean: float, gsd2: float) -> tuple[float, float]:
    """
    Convert (mean, GSD²) to lognormal (mu, sigma) parameters.

    sigma_ln = ln(sqrt(GSD²)) = 0.5 * ln(GSD²)
    mu_ln    = ln(mean) - sigma_ln² / 2

    Returns (mu_ln, sigma_ln).
    """
    if mean == 0.0:
        return (0.0, 0.0)
    sigma_ln = 0.5 * math.log(gsd2)
    mu_ln = math.log(abs(mean)) - 0.5 * sigma_ln ** 2
    return (mu_ln, sigma_ln)


def _sample_lognormal(mu: float, sigma: float, n: int, rng) -> list[float]:
    """Draw n samples from lognormal(mu, sigma) using the provided RNG."""
    import random as _random
    samples = []
    for _ in range(n):
        z = rng.gauss(0.0, 1.0)
        samples.append(math.exp(mu + sigma * z))
    return samples


def monte_carlo_uncertainty(
    model_func: Callable[..., float],
    distributions: dict[str, dict[str, float]],
    n_samples: int = 10_000,
    *,
    seed: int | None = 42,
    ci_level: float = 0.90,
) -> dict[str, Any]:
    """
    Propagate parameter uncertainty through a model via Monte Carlo simulation.

    Args:
        model_func: callable(**kwargs) → float
            Receives one realisation of each parameter and returns a scalar.
        distributions: {param_name: {"mean": float, "gsd2": float}}
            Each entry describes a lognormal distribution for one parameter.
        n_samples: number of Monte Carlo draws (default 10 000).
        seed: random seed for reproducibility (default 42; None = random).
        ci_level: confidence interval level (default 0.90 → 5th–95th percentile).

    Returns:
        {
            "mean":   float,
            "median": float,
            "std":    float,
            "ci_low": float,   # lower bound of ci_level CI
            "ci_high": float,  # upper bound of ci_level CI
            "n_samples": int,
            "ci_level": float,
        }

    Example:
        >>> def gwp(aluminium_factor, mass):
        ...     return aluminium_factor * mass
        >>> result = monte_carlo_uncertainty(
        ...     gwp,
        ...     distributions={
        ...         "aluminium_factor": {"mean": 9.16, "gsd2": 1.05},
        ...         "mass": {"mean": 1.0, "gsd2": 1.10},
        ...     },
        ...     n_samples=5000,
        ... )
    """
    import random as _random

    rng = _random.Random(seed)

    # Pre-generate samples for each parameter
    param_samples: dict[str, list[float]] = {}
    for param, dist in distributions.items():
        mean = float(dist["mean"])
        gsd2 = float(dist.get("gsd2", _GSD2_FALLBACK))
        if mean == 0.0 or gsd2 <= 1.0:
            # Deterministic — all samples equal mean
            param_samples[param] = [mean] * n_samples
        else:
            mu, sigma = lognormal_params(mean, gsd2)
            raw = _sample_lognormal(mu, sigma, n_samples, rng)
            # Preserve sign of original mean
            sign = 1.0 if mean >= 0 else -1.0
            param_samples[param] = [sign * v for v in raw]

    # Run model for each sample
    outputs: list[float] = []
    for i in range(n_samples):
        kwargs = {p: param_samples[p][i] for p in distributions}
        try:
            val = model_func(**kwargs)
            outputs.append(float(val))
        except Exception:
            pass  # skip failed evaluations

    if not outputs:
        raise ValueError("All Monte Carlo evaluations failed.")

    outputs_sorted = sorted(outputs)
    n = len(outputs_sorted)

    tail = (1.0 - ci_level) / 2.0
    lo_idx = max(0, int(math.floor(tail * n)))
    hi_idx = min(n - 1, int(math.ceil((1.0 - tail) * n)) - 1)

    return {
        "mean": statistics.mean(outputs),
        "median": statistics.median(outputs),
        "std": statistics.pstdev(outputs),
        "ci_low": outputs_sorted[lo_idx],
        "ci_high": outputs_sorted[hi_idx],
        "n_samples": n,
        "ci_level": ci_level,
    }


def impact_uncertainty_bounds(
    impact_value: float,
    category: str,
) -> dict[str, float]:
    """
    Quick lognormal ±90% CI for a single impact value given a category's GSD².

    Args:
        impact_value: central estimate (mean) of the impact.
        category: impact category key (gwp100, ap, ep, htp, water, pm25).

    Returns:
        {mean, ci_low, ci_high, gsd2}
    """
    gsd2 = gsd2_for_category(category)
    if impact_value == 0.0 or gsd2 <= 1.0:
        return {"mean": impact_value, "ci_low": impact_value,
                "ci_high": impact_value, "gsd2": gsd2}

    sigma_ln = 0.5 * math.log(gsd2)
    # 90% CI: 5th–95th percentile of lognormal
    # P5 = exp(mu_ln - 1.645 * sigma_ln), P95 = exp(mu_ln + 1.645 * sigma_ln)
    # Since mean = exp(mu_ln + 0.5*sigma_ln²):
    mu_ln = math.log(abs(impact_value)) - 0.5 * sigma_ln ** 2
    sign = 1.0 if impact_value >= 0 else -1.0
    ci_low = sign * math.exp(mu_ln - 1.645 * sigma_ln)
    ci_high = sign * math.exp(mu_ln + 1.645 * sigma_ln)

    return {
        "mean": impact_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "gsd2": gsd2,
    }
