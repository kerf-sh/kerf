"""
kerf_cad_core.topology.multi_load
==================================
Multi-load-case compliance aggregation and Pareto-front utilities for
density-based topology optimisation (SIMP).  All functions are **pure Python**
(stdlib math only); no numpy, no scipy, no FEniCSx dependency.

Overview
--------
In a single-load SIMP formulation the objective is the structural compliance

    C = F^T u = u^T K(rho) u

under one applied load vector *F*.  When a structure must perform under
several independent loading scenarios (e.g. horizontal + vertical forces on a
bracket, or multiple traffic patterns on a bridge deck) the single-load
objective is inadequate.

Two standard approaches are provided:

weighted_compliance
    Compute the **weighted sum** of compliances across N load cases:

        C_total = sum_i  w_i * C_i(rho)

    This collapses the multi-load problem to a single scalar that the
    standard OC / MMA update can minimise.  The choice of weights *w_i*
    reflects the designer's relative importance of each scenario.

accumulate_sensitivity
    Accumulate the compliance-sensitivity contributions from each load case:

        dC_total / drho_e  = sum_i  w_i * dC_i / drho_e

    so the gradient used by the density-update scheme is the correct total
    derivative of the weighted objective.

pareto_two_load
    Sweep the weight ratio ``(w_1, 1 - w_1)`` across N steps and collect
    the resulting ``(C_1, C_2)`` Pareto-front sketch.  Returns the front
    as a list of ``{"w1": w, "C1": c1, "C2": c2}`` dicts sorted by w1.

    This is a *sketch* rather than a rigorous Pareto computation: it
    samples the weighted-sum Pareto boundary by varying the scalar weight,
    which identifies the *connected* part of the front.  Non-convex regions
    of the true Pareto set are not captured, but for SIMP problems with
    convex load cases the weighted-sum front coincides with the true Pareto
    boundary (Das & Dennis, 1997).

References
----------
* Sigmund (2001) A 99 line topology optimization code. SMO 21, 120-127.
* Hvejsel & Lund (2011) Material interpolation schemes for unified topology
  and multi-material optimization. SMO 43, 811-825.
* Das & Dennis (1997) A closer look at drawbacks of minimising weighted sums
  of objectives for Pareto set generation. SMO 14, 63-69.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Weighted compliance aggregation
# ---------------------------------------------------------------------------

def weighted_compliance(
    compliances: Sequence[float],
    weights: Sequence[float],
) -> float:
    """Return the weighted sum of per-load-case compliances.

    Parameters
    ----------
    compliances:
        Scalar compliance value for each load case, length N.
    weights:
        Non-negative importance weights, length N.  Need not sum to 1.

    Returns
    -------
    c_total:
        Sum of ``w_i * C_i``.

    Raises
    ------
    ValueError
        If *compliances* and *weights* have different lengths, or any weight
        is negative.
    """
    if len(compliances) != len(weights):
        raise ValueError(
            f"compliances ({len(compliances)}) and weights ({len(weights)}) "
            "must have the same length."
        )
    for i, w in enumerate(weights):
        if w < 0.0:
            raise ValueError(f"weights[{i}] = {w!r} is negative.")
    return sum(float(w) * float(c) for w, c in zip(weights, compliances))


def accumulate_sensitivity(
    sensitivities: Sequence[Sequence[float]],
    weights: Sequence[float],
) -> List[float]:
    """Accumulate per-load-case compliance sensitivities into a total gradient.

    Parameters
    ----------
    sensitivities:
        List of N per-element sensitivity arrays, each of length ``nel``
        (the number of finite-element mesh cells).
    weights:
        Importance weights, length N, same order as *sensitivities*.

    Returns
    -------
    dc_total:
        Length-``nel`` array: ``dc_total[e] = sum_i w_i * dc_i[e]``.

    Raises
    ------
    ValueError
        If the inner arrays have inconsistent lengths, or len(sensitivities)
        != len(weights).
    """
    if len(sensitivities) != len(weights):
        raise ValueError(
            f"sensitivities ({len(sensitivities)}) and weights ({len(weights)}) "
            "must have the same length."
        )
    if not sensitivities:
        return []
    nel = len(sensitivities[0])
    for i, s in enumerate(sensitivities):
        if len(s) != nel:
            raise ValueError(
                f"sensitivities[{i}] has length {len(s)}, expected {nel}."
            )
    dc = [0.0] * nel
    for w, sens in zip(weights, sensitivities):
        wf = float(w)
        for e in range(nel):
            dc[e] += wf * float(sens[e])
    return dc


# ---------------------------------------------------------------------------
# Two-load Pareto-front sketch
# ---------------------------------------------------------------------------

def pareto_two_load(
    solve_fn: Callable[[float, float], Tuple[float, float]],
    n_points: int = 11,
) -> Dict[str, Any]:
    """Sweep the weight pair ``(w1, w2 = 1 - w1)`` and collect a Pareto sketch.

    *solve_fn(w1, w2)* should return ``(C1, C2)`` — the compliances under
    load 1 and load 2 respectively for a structure optimised under the
    weighted objective ``w1 * C1_struct + w2 * C2_struct``.  The caller is
    responsible for the actual FE + SIMP solve; this function only sweeps
    the weight space and collects results.

    Parameters
    ----------
    solve_fn:
        Callable ``(w1: float, w2: float) -> (C1: float, C2: float)``.
    n_points:
        Number of equally-spaced weight samples including the endpoints
        ``(w1=0, w1=1)``.  Must be >= 2.

    Returns
    -------
    dict with keys:

    ``"ok"`` (bool)
        True if the sweep completed without errors.
    ``"front"``
        List of ``{"w1": float, "w2": float, "C1": float, "C2": float}``
        sorted by ascending *w1*.
    ``"trade_off_exists"`` (bool)
        True iff the optimal design for load 1 alone (``w1 = 1``) is
        strictly worse under load 2 than the optimal design for load 2 alone
        (``w1 = 0``), confirming a genuine trade-off.
    ``"reason"`` (str, only when ``"ok"`` is False)
        Human-readable error description.
    """
    if n_points < 2:
        return {"ok": False, "reason": "n_points must be >= 2"}

    front: List[Dict[str, float]] = []
    try:
        step = 1.0 / (n_points - 1)
        for i in range(n_points):
            w1 = round(i * step, 10)
            w2 = round(1.0 - w1, 10)
            # Clamp numerical noise at endpoints.
            w1 = max(0.0, min(1.0, w1))
            w2 = max(0.0, min(1.0, w2))
            c1, c2 = solve_fn(w1, w2)
            front.append({
                "w1": float(w1),
                "w2": float(w2),
                "C1": float(c1),
                "C2": float(c2),
            })
    except Exception as exc:
        return {"ok": False, "reason": f"solve_fn raised: {exc}"}

    # Sort by w1 ascending (caller may have returned results out of order).
    front.sort(key=lambda p: p["w1"])

    # Check for a genuine trade-off: structure tuned for load 1 (w1=1, w2=0)
    # should be strictly more compliant under load 2 than a structure tuned
    # for load 2 alone (w1=0, w2=1).
    c2_at_w1_one = front[-1]["C2"]   # load-2 compliance when optimised for load 1
    c2_at_w1_zero = front[0]["C2"]   # load-2 compliance when optimised for load 2
    trade_off = c2_at_w1_one > c2_at_w1_zero * (1.0 + 1e-9)

    return {
        "ok": True,
        "front": front,
        "n_points": len(front),
        "trade_off_exists": trade_off,
    }


# ---------------------------------------------------------------------------
# Utility: normalise weights
# ---------------------------------------------------------------------------

def normalise_weights(weights: Sequence[float]) -> List[float]:
    """Return a copy of *weights* scaled so that the sum equals 1.

    Parameters
    ----------
    weights:
        Non-negative importance weights.

    Returns
    -------
    normalised:
        Weights scaled to sum to 1.0.

    Raises
    ------
    ValueError
        If *weights* is empty, any value is negative, or the sum is zero.
    """
    if not weights:
        raise ValueError("weights must not be empty.")
    total = 0.0
    for i, w in enumerate(weights):
        if w < 0.0:
            raise ValueError(f"weights[{i}] = {w!r} is negative.")
        total += float(w)
    if total <= 0.0:
        raise ValueError("Sum of weights is zero; cannot normalise.")
    return [float(w) / total for w in weights]


# ---------------------------------------------------------------------------
# Load-case container (lightweight value type)
# ---------------------------------------------------------------------------

class LoadCase:
    """Lightweight container for a single structural load case.

    Attributes
    ----------
    F:
        Global force vector (length == ndof).
    fixed:
        List of fixed (constrained) global DOF indices.
    name:
        Optional human-readable identifier.
    weight:
        Importance weight for weighted-compliance aggregation.  Defaults
        to 1.0; can be re-scaled later via :func:`normalise_weights`.
    """

    __slots__ = ("F", "fixed", "name", "weight")

    def __init__(
        self,
        F: List[float],
        fixed: List[int],
        *,
        name: str = "",
        weight: float = 1.0,
    ) -> None:
        if weight < 0.0:
            raise ValueError(f"LoadCase weight must be non-negative, got {weight!r}.")
        self.F: List[float] = list(F)
        self.fixed: List[int] = list(fixed)
        self.name: str = str(name)
        self.weight: float = float(weight)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LoadCase(name={self.name!r}, weight={self.weight}, "
            f"ndof={len(self.F)}, n_fixed={len(self.fixed)})"
        )


# ---------------------------------------------------------------------------
# Compliance sensitivity for a single load case
# ---------------------------------------------------------------------------

def element_sensitivity(
    xphys: Sequence[float],
    ce: Sequence[float],
    penal: float,
    Emin: float = 1e-9,
) -> List[float]:
    """Compute the (negative) compliance sensitivity for one load case.

    Under the SIMP interpolation ``E(rho) = Emin + rho^p * (1 - Emin)``
    the derivative of the element strain energy with respect to the physical
    density is:

        dC_e / drho_e  = -p * rho_e^(p-1) * (1 - Emin) * u_e^T KE u_e

    The sign convention follows Sigmund (2001): we return a **negative**
    value so that the OC / MMA minimiser simply uses ``-dc`` as the
    driving force.

    Parameters
    ----------
    xphys:
        Physical (filtered) element densities.
    ce:
        Per-element strain energy density ``u_e^T KE u_e`` (unit modulus).
    penal:
        SIMP penalisation exponent (typically 3.0).
    Emin:
        Small modulus for void elements (prevents singularity).

    Returns
    -------
    dc:
        Length-``nel`` array of ``dC / drho_e`` values (all non-positive).
    """
    nel = len(xphys)
    if len(ce) != nel:
        raise ValueError(
            f"xphys ({nel}) and ce ({len(ce)}) must have the same length."
        )
    dc: List[float] = [0.0] * nel
    for e in range(nel):
        rho = float(xphys[e])
        if rho < 1e-12:
            dc[e] = 0.0
        else:
            dscale = penal * (rho ** (penal - 1.0)) * (1.0 - Emin)
            dc[e] = -dscale * float(ce[e])
    return dc
