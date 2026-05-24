"""
kerf_cad_core.matsel.multi_objective — Pareto-style multi-objective material selection.

Provides three complementary algorithms for multi-objective material selection,
analogous to the Granta CES Selector "Level 3" capabilities:

  pareto_frontier(materials, objectives, directions)
      Returns the non-dominated (Pareto-optimal) set.  A material is dominated
      if another material is at least as good on every objective and strictly
      better on at least one.

  weighted_score(materials, objectives, weights, normalise=True)
      Linear weighted-sum ranking.  With normalise=True each objective is first
      min-max scaled to [0, 1] so that objectives with different magnitudes can
      be compared fairly.  A single weight reduces to a single-objective Ashby
      ranking.

  tradeoff_envelope(materials, x_metric, y_metric)
      Computes the points on the convex Pareto envelope (upper-right hull for
      two maximise objectives, or the appropriate quadrant for mixed directions).
      Suitable for plotting on an Ashby chart.

All three functions work on the *full* database (base + extended) by default,
but accept an explicit dict of materials for flexibility.

Property retrieval
------------------
The functions accept property names from both the base property set and the
computed Ashby merit indices, via a thin shim that calls db._get_prop_value
for the base+derived indices, and also supports 'co2_kg_kg' and
'specific_heat' from the extended entries.

Functions never raise; errors are returned in {"ok": False, "reason": "..."}.

References
----------
Ashby, M.F. "Materials Selection in Mechanical Design", 5th ed. (2017),
Chapter 9 — Multiple constraints and objectives; Chapter 11 — Pareto fronts.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

from kerf_cad_core.matsel.db import _DB as _BASE_DB, _derived, _BASE_PROPS, _DERIVED_PROPS


# ---------------------------------------------------------------------------
# Property resolution
# ---------------------------------------------------------------------------

def _get_val(name: str, props: dict[str, Any], metric: str) -> float | None:
    """Resolve a property value for *metric* from *props*.

    Supports:
      • All base properties (density, E, sigma_y, …)
      • All derived Ashby indices (specific_stiffness, …) via db._derived
      • Extended properties: co2_kg_kg, specific_heat (stored directly in props)
    Returns None if the property is unknown or missing.
    """
    if metric in _BASE_PROPS:
        v = props.get(metric)
        return float(v) if v is not None else None

    if metric in _DERIVED_PROPS:
        # _derived expects the canonical *base* db entry but the extended db has
        # the same schema; pass props directly.
        d = _derived(name, props)
        return d.get(metric)

    # Extended / optional properties stored directly on the entry
    v = props.get(metric)
    if v is not None:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_db(materials: dict[str, dict] | None) -> dict[str, dict]:
    """Return the full database if *materials* is None, else *materials*."""
    if materials is not None:
        return materials
    # Import lazily to avoid circular imports at module-init time
    from kerf_cad_core.matsel.extended_db import get_full_db
    return get_full_db()


def _dominates(a_vals: list[float], b_vals: list[float], directions: list[str]) -> bool:
    """Return True if vector *a* dominates vector *b*.

    *a* dominates *b* iff:
      - For every objective i: a is no worse than b (in the direction sense), AND
      - For at least one objective i: a is strictly better than b.
    """
    at_least_as_good = True
    strictly_better = False
    for av, bv, direction in zip(a_vals, b_vals, directions):
        if direction == "min":
            if av > bv:
                at_least_as_good = False
                break
            if av < bv:
                strictly_better = True
        else:  # "max"
            if av < bv:
                at_least_as_good = False
                break
            if av > bv:
                strictly_better = True
    return at_least_as_good and strictly_better


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pareto_frontier(
    objectives: list[str],
    directions: list[str],
    materials: dict[str, dict] | None = None,
) -> dict:
    """Return the non-dominated (Pareto-optimal) set of materials.

    Parameters
    ----------
    objectives : list[str]
        Property / merit-index names to optimise, e.g. ["density", "E"].
    directions : list[str]
        "min" or "max" for each corresponding objective.
    materials : dict[str, dict] | None
        Material database to use.  None → full database (base + extended).

    Returns
    -------
    dict
        ok       : True
        frontier : list of {"name": str, "values": {obj: val, ...}} dicts
                   representing the non-dominated set, sorted by first objective.
        dominated: count of dominated materials.
        warnings : list of warning strings.

    Never raises.
    """
    warnings: list[str] = []

    # Validate
    if not objectives:
        return {"ok": False, "reason": "objectives list is empty"}
    if len(objectives) != len(directions):
        return {"ok": False, "reason": "objectives and directions must have the same length"}
    for d in directions:
        if d not in ("min", "max"):
            return {"ok": False, "reason": f"direction must be 'min' or 'max', got {d!r}"}

    db = _resolve_db(materials)

    # Collect numeric vectors
    mat_vals: list[tuple[str, list[float]]] = []  # (name, [val_per_obj])
    for name, props in db.items():
        vals: list[float] = []
        skip = False
        for obj in objectives:
            v = _get_val(name, props, obj)
            if v is None or not math.isfinite(v):
                skip = True
                warnings.append(f"{name}: missing/non-finite value for {obj!r} — excluded.")
                break
            vals.append(v)
        if not skip:
            mat_vals.append((name, vals))

    if not mat_vals:
        return {"ok": True, "frontier": [], "dominated": 0, "warnings": warnings}

    # Pareto filter — O(n²) which is fine for n ≤ ~1000
    dominated_set: set[str] = set()
    for i, (name_a, vals_a) in enumerate(mat_vals):
        for j, (name_b, vals_b) in enumerate(mat_vals):
            if i == j:
                continue
            if _dominates(vals_b, vals_a, directions):
                dominated_set.add(name_a)
                break  # a is dominated; no need to check further dominators

    frontier = [
        {
            "name": name,
            "values": {obj: val for obj, val in zip(objectives, vals)},
        }
        for name, vals in mat_vals
        if name not in dominated_set
    ]

    # Sort frontier by first objective (ascending for min, descending for max)
    asc = directions[0] == "min"
    frontier.sort(key=lambda x: x["values"][objectives[0]], reverse=(not asc))

    return {
        "ok": True,
        "frontier": frontier,
        "dominated": len(dominated_set),
        "warnings": warnings,
    }


def weighted_score(
    objectives: list[str],
    weights: list[float],
    directions: list[str] | None = None,
    normalise: bool = True,
    top_n: int | None = None,
    materials: dict[str, dict] | None = None,
) -> dict:
    """Rank materials by a linear weighted sum of objectives.

    When *normalise* is True, each objective is min-max scaled to [0, 1]
    (with sign flipped for "min" objectives so that higher score is always
    better) before weighting.  This reproduces the existing Ashby ranking when
    a single non-zero weight is provided for a single objective.

    Parameters
    ----------
    objectives : list[str]
        Property / merit-index names.
    weights : list[float]
        Non-negative weight for each objective.  Need not sum to 1.
    directions : list[str] | None
        "min" or "max" per objective.  If None, "max" is assumed for derived
        Ashby indices and "min" for density / cost / CTE (matching db.py
        _LOWER_IS_BETTER convention).
    normalise : bool
        If True (default), min-max normalise each objective before weighting.
    top_n : int | None
        Return at most this many results.  None → all.
    materials : dict[str, dict] | None
        Database override.  None → full database.

    Returns
    -------
    dict
        ok      : True
        ranked  : list of {"name", "score", "rank", "values"} dicts, best first.
        warnings: list of warning strings.

    Never raises.
    """
    from kerf_cad_core.matsel.db import _LOWER_IS_BETTER  # local import

    warnings: list[str] = []

    if not objectives:
        return {"ok": False, "reason": "objectives list is empty"}
    if len(objectives) != len(weights):
        return {"ok": False, "reason": "objectives and weights must have the same length"}
    if any(w < 0 for w in weights):
        return {"ok": False, "reason": "all weights must be non-negative"}

    # Infer directions if not supplied
    if directions is None:
        directions = [
            "min" if obj in _LOWER_IS_BETTER else "max"
            for obj in objectives
        ]
    if len(directions) != len(objectives):
        return {"ok": False, "reason": "objectives and directions must have the same length"}
    for d in directions:
        if d not in ("min", "max"):
            return {"ok": False, "reason": f"direction must be 'min' or 'max', got {d!r}"}

    db = _resolve_db(materials)

    # Collect vectors
    mat_vals: list[tuple[str, list[float]]] = []
    for name, props in db.items():
        vals: list[float] = []
        skip = False
        for obj in objectives:
            v = _get_val(name, props, obj)
            if v is None or not math.isfinite(v):
                skip = True
                warnings.append(f"{name}: missing/non-finite value for {obj!r} — excluded.")
                break
            vals.append(v)
        if not skip:
            mat_vals.append((name, vals))

    if not mat_vals:
        return {"ok": True, "ranked": [], "warnings": warnings}

    n_obj = len(objectives)

    # Compute per-objective min/max for normalisation
    if normalise:
        mins = [min(vals[i] for _, vals in mat_vals) for i in range(n_obj)]
        maxs = [max(vals[i] for _, vals in mat_vals) for i in range(n_obj)]
    else:
        mins = [0.0] * n_obj
        maxs = [1.0] * n_obj  # unused when normalise=False

    def _normalised(raw: float, i: int) -> float:
        lo, hi = mins[i], maxs[i]
        if hi == lo:
            return 0.5  # degenerate: all materials equal on this objective
        return (raw - lo) / (hi - lo)

    scores: list[tuple[str, float, list[float]]] = []
    for name, vals in mat_vals:
        score = 0.0
        for i, (obj, w, direction) in enumerate(zip(objectives, weights, directions)):
            if normalise:
                norm = _normalised(vals[i], i)
            else:
                norm = vals[i]
            # Flip so higher normalised score is always better
            if direction == "min":
                norm = 1.0 - norm if normalise else -norm
            score += w * norm
        scores.append((name, score, vals))

    scores.sort(key=lambda x: x[1], reverse=True)

    if top_n is not None:
        try:
            scores = scores[: int(top_n)]
        except (TypeError, ValueError):
            warnings.append(f"top_n {top_n!r} is not valid — returning all.")

    ranked = [
        {
            "name": name,
            "score": sc,
            "rank": rank + 1,
            "values": {obj: val for obj, val in zip(objectives, vals)},
        }
        for rank, (name, sc, vals) in enumerate(scores)
    ]

    return {"ok": True, "ranked": ranked, "warnings": warnings}


def tradeoff_envelope(
    x_metric: str,
    y_metric: str,
    x_direction: str = "max",
    y_direction: str = "max",
    materials: dict[str, dict] | None = None,
) -> dict:
    """Compute the Pareto envelope for an Ashby (x vs y) chart.

    Returns the non-dominated (Pareto-optimal) subset of materials with respect
    to the two specified objectives and directions.  A material is on the
    envelope if no other material is simultaneously better (or equal) on both
    x and y in their respective optimisation directions.

    This is analogous to the Granta/CES Selector trade-off surface for two
    objectives; these are the materials an engineer should consider when making
    an Ashby chart — every point off the envelope is strictly worse on both
    objectives than some envelope member.

    For the special case where both directions are "max", the envelope
    corresponds to the upper-right Pareto frontier on the Ashby chart.

    Parameters
    ----------
    x_metric, y_metric : str
        Property / merit-index for the chart axes.
    x_direction, y_direction : "min" | "max"
        Optimisation direction for each axis.
    materials : dict[str, dict] | None
        Database override.

    Returns
    -------
    dict
        ok       : True
        envelope : list of {"name", "x", "y"} dicts on the Pareto boundary,
                   sorted by x ascending.
        all_points: list of {"name", "x", "y"} for all materials with valid data.
        warnings : list of warning strings.

    Never raises.
    """
    warnings: list[str] = []

    for label, d in (("x_direction", x_direction), ("y_direction", y_direction)):
        if d not in ("min", "max"):
            return {"ok": False, "reason": f"{label} must be 'min' or 'max', got {d!r}"}

    db = _resolve_db(materials)

    # Collect (x, y) pairs
    points: list[dict] = []
    for name, props in db.items():
        xv = _get_val(name, props, x_metric)
        yv = _get_val(name, props, y_metric)
        if xv is None or yv is None or not math.isfinite(xv) or not math.isfinite(yv):
            continue
        points.append({"name": name, "x": xv, "y": yv})

    if not points:
        return {"ok": True, "envelope": [], "all_points": [], "warnings": warnings}

    # Use the Pareto-dominance approach: a point is on the envelope iff
    # it is not dominated by any other point with respect to both objectives.
    # This is exactly pareto_frontier for 2 objectives, but operating on
    # the already-resolved (x, y) pairs.
    directions = [x_direction, y_direction]

    def _dom(a: dict, b: dict) -> bool:
        """Return True if b dominates a."""
        vals_a = [a["x"], a["y"]]
        vals_b = [b["x"], b["y"]]
        return _dominates(vals_b, vals_a, directions)

    dominated: set[str] = set()
    for i, pa in enumerate(points):
        for j, pb in enumerate(points):
            if i == j:
                continue
            if _dom(pa, pb):
                dominated.add(pa["name"])
                break

    envelope = [p for p in points if p["name"] not in dominated]
    envelope.sort(key=lambda p: p["x"])
    all_points_sorted = sorted(points, key=lambda p: p["x"])

    return {
        "ok": True,
        "envelope": envelope,
        "all_points": all_points_sorted,
        "warnings": warnings,
    }
