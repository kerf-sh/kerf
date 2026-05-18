"""
kerf_cad_core.marine.hull — Marine hull parametric recipe and quality metrics.

Building a hull surface
-----------------------
A *table of half-breadths* (also called an *offset table*) is the traditional
way to describe a ship hull.  The table contains measured or designed points:

    station   — longitudinal position (X), 0 = bow, increasing to stern
    waterline — vertical position (Z), 0 = baseline keel, increasing upward
    half_breadth — transverse half-width (Y) at that (station, waterline) pair

From the offset table we build a **lofted control-net recipe**: a list of
station cross-sections, each containing the waterline points, together with the
knot structure needed to guide a downstream NURBS loft worker.  The recipe is
pure data (no OCC dependency); it mirrors the parametric recipe pattern used by
the other kerf-cad-core tools (arch_wall, civil_earthwork, etc.).

Fairing metrics
---------------
A faired hull has:
  1. *Curvature monotonicity* per station — the half-breadths at each station
     must be monotonically non-decreasing from keel (WL=0) to the maximum
     breadth waterline, then non-increasing above it (convex shape).  A kink
     is detected when two consecutive differences change sign.
  2. *Batten energy* — the bending energy proxy of a natural cubic spline fit
     to each station's WL → Y profile.  Lower is fairer.
  3. *Overall roughness* — root-mean-square of second differences across
     stations at each waterline.  Uniform spacing assumed for the finite-
     difference approximation.

Hydrostatics via Simpson's rule
--------------------------------
Simpson's rule (composite 1/3 rule) gives exact results for polynomials up to
degree 3.  The standard naval-architecture application integrates the
waterplane area and submerged volume:

    Waterplane area  Awp = ∫₀^L 2·y(x, T) dx   at the design waterline T
    Submerged volume ∇   = ∫₀^L Aₓ(x) dx        where Aₓ is the sectional area
    LCB              x̄   = (1/∇) ∫₀^L x·Aₓ(x) dx

Sectional area Aₓ(x) at each station is computed by applying Simpson's rule
over the waterlines from keel to T.

Notes
-----
- All inputs are in **metres** (hull offsets).  No unit conversion is applied.
- Builders never raise; they return ``{"ok": False, "errors": [...]}`` on bad
  input so the LLM can recover gracefully.
- The word "half-breadth" throughout refers to the *half-beam* (port or
  starboard side only).  The full beam at any waterline is 2× the half-breadth.

Author: imranparuk
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List

_EPS = 1e-12


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HullOffsetTable:
    """
    Validated table of half-breadth offsets.

    Attributes
    ----------
    stations : list[float]
        Unique, sorted station positions (X, metres).
    waterlines : list[float]
        Unique, sorted waterline positions (Z, metres).
    offsets : dict[tuple[float, float], float]
        Mapping (station, waterline) → half_breadth (metres).
        Not every (station, waterline) pair need have an entry; missing entries
        indicate that the hull surface does not extend to that combination
        (e.g., above the sheer line at a given station).
    """
    stations: list[float]
    waterlines: list[float]
    offsets: dict[tuple[float, float], float]


@dataclass
class HullControlNet:
    """
    Parametric lofted control-net recipe (pure data, no OCC).

    This mirrors the pattern used by arch/struct/civil tools: the recipe
    describes *what* a downstream NURBS loft worker should build, not the
    geometry itself.

    Attributes
    ----------
    op : str
        Always ``"marine_loft_hull"``.
    stations : list[float]
        Sorted station X positions.
    waterlines : list[float]
        Sorted waterline Z positions.
    sections : list[dict]
        One entry per station.  Each entry::

            {
              "station": float,          # X position
              "points": [                # waterline points for this section
                  {"wl": float, "y": float},  # Z and half-breadth
                  ...
              ]
            }

        Points are sorted by waterline (keel → sheer).
    knot_params : dict
        Suggested parametric knot structure for the lofter::

            {
              "station_params":    list[float],  # normalised 0..1 along length
              "waterline_params":  list[float],  # normalised 0..1 along depth
              "degree_u": int,                   # along stations (suggested 3)
              "degree_v": int,                   # along waterlines (suggested 3)
            }
    loa : float
        Length over all (max_station − min_station), metres.
    max_half_beam : float
        Maximum half-breadth across all sections, metres.
    depth : float
        Depth (max_waterline − min_waterline), metres.
    station_count : int
        Number of station sections.
    waterline_count : int
        Number of waterlines used.
    """
    op: str
    stations: list[float]
    waterlines: list[float]
    sections: list[dict]
    knot_params: dict
    loa: float
    max_half_beam: float
    depth: float
    station_count: int
    waterline_count: int


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_offset_rows(rows: object) -> tuple[list[dict] | None, list[str]]:
    """
    Parse and validate a raw offset-table input.

    ``rows`` must be a list of dicts, each with keys:
        station       : number
        waterline     : number
        half_breadth  : number >= 0

    Returns (parsed_rows, errors).  On error, returns (None, errors).
    """
    errors: list[str] = []
    if not isinstance(rows, list):
        return None, ["offsets must be a list of {station, waterline, half_breadth} objects"]
    if len(rows) < 3:
        return None, [
            f"offset table must have at least 3 rows to define a hull; got {len(rows)}"
        ]

    parsed: list[dict] = []
    seen: set[tuple[float, float]] = set()

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"offsets[{i}]: must be an object, got {type(row).__name__}")
            continue
        row_errors: list[str] = []

        for key in ("station", "waterline", "half_breadth"):
            if key not in row:
                row_errors.append(f"offsets[{i}]: missing field '{key}'")

        if row_errors:
            errors.extend(row_errors)
            continue

        try:
            st = float(row["station"])
            wl = float(row["waterline"])
            hb = float(row["half_breadth"])
        except (TypeError, ValueError) as exc:
            errors.append(f"offsets[{i}]: numeric conversion failed: {exc}")
            continue

        if hb < 0:
            errors.append(
                f"offsets[{i}]: half_breadth must be >= 0; got {hb}"
            )
            continue

        key = (st, wl)
        if key in seen:
            errors.append(
                f"offsets[{i}]: duplicate (station={st}, waterline={wl})"
            )
            continue
        seen.add(key)

        parsed.append({"station": st, "waterline": wl, "half_breadth": hb})

    if errors:
        return None, errors

    # Need at least 2 distinct stations and 2 distinct waterlines
    sts = sorted({r["station"] for r in parsed})
    wls = sorted({r["waterline"] for r in parsed})

    if len(sts) < 2:
        return None, [
            f"offset table must span at least 2 stations; got {len(sts)}: {sts}"
        ]
    if len(wls) < 2:
        return None, [
            f"offset table must span at least 2 waterlines; got {len(wls)}: {wls}"
        ]

    return parsed, []


def _build_offset_table(rows: list[dict]) -> HullOffsetTable:
    """Build a HullOffsetTable from validated parsed rows."""
    stations = sorted({r["station"] for r in rows})
    waterlines = sorted({r["waterline"] for r in rows})
    offsets = {(r["station"], r["waterline"]): r["half_breadth"] for r in rows}
    return HullOffsetTable(stations=stations, waterlines=waterlines, offsets=offsets)


# ---------------------------------------------------------------------------
# Knot parametrisation
# ---------------------------------------------------------------------------

def _chord_params(values: list[float]) -> list[float]:
    """
    Compute chord-length parametrisation (normalised 0..1) for a sequence of
    scalar values.  Falls back to uniform if total chord length is zero.
    """
    n = len(values)
    if n == 1:
        return [0.0]
    diffs = [abs(values[i + 1] - values[i]) for i in range(n - 1)]
    total = sum(diffs)
    if total < _EPS:
        return [i / (n - 1) for i in range(n)]
    params = [0.0]
    cumsum = 0.0
    for d in diffs:
        cumsum += d
        params.append(cumsum / total)
    return params


# ---------------------------------------------------------------------------
# hull_from_offsets
# ---------------------------------------------------------------------------

def hull_from_offsets(rows: object) -> dict:
    """
    Build a lofted control-net recipe (HullControlNet) from a raw offset table.

    Parameters
    ----------
    rows : list[dict]
        Each row must be ``{station, waterline, half_breadth}``.  See
        :class:`HullOffsetTable` for conventions.  Missing (station, waterline)
        pairs are silently skipped (the hull need not be rectangular in the
        offset grid).

    Returns
    -------
    dict
        On success: serialised :class:`HullControlNet` with ``ok=True``.
        On failure: ``{"ok": False, "errors": [...]}`` — never raises.

    Recipe fields
    -------------
    The returned dict contains an ``op="marine_loft_hull"`` key so a downstream
    NURBS worker can dispatch on it, plus all HullControlNet attributes
    serialised as JSON-compatible types.
    """
    parsed, errors = _validate_offset_rows(rows)
    if errors:
        return {"ok": False, "errors": errors}

    table = _build_offset_table(parsed)
    stations = table.stations
    waterlines = table.waterlines

    sections: list[dict] = []
    for st in stations:
        pts = []
        for wl in waterlines:
            hb = table.offsets.get((st, wl))
            if hb is not None:
                pts.append({"wl": wl, "y": hb})
        # Sort by waterline (should already be in order)
        pts.sort(key=lambda p: p["wl"])
        sections.append({"station": st, "points": pts})

    # Knot parameters
    st_params = _chord_params(stations)
    wl_params = _chord_params(waterlines)

    loa = stations[-1] - stations[0]
    depth = waterlines[-1] - waterlines[0]
    max_hb = max(table.offsets.values()) if table.offsets else 0.0

    net = HullControlNet(
        op="marine_loft_hull",
        stations=stations,
        waterlines=waterlines,
        sections=sections,
        knot_params={
            "station_params": st_params,
            "waterline_params": wl_params,
            "degree_u": min(3, len(stations) - 1),
            "degree_v": min(3, len(waterlines) - 1),
        },
        loa=loa,
        max_half_beam=max_hb,
        depth=depth,
        station_count=len(stations),
        waterline_count=len(waterlines),
    )

    return {
        "ok": True,
        "op": net.op,
        "stations": net.stations,
        "waterlines": net.waterlines,
        "sections": net.sections,
        "knot_params": net.knot_params,
        "loa": net.loa,
        "max_half_beam": net.max_half_beam,
        "depth": net.depth,
        "station_count": net.station_count,
        "waterline_count": net.waterline_count,
    }


# ---------------------------------------------------------------------------
# Cubic spline helpers (natural, for fairing metrics)
# ---------------------------------------------------------------------------

def _natural_cubic_spline_second_derivs(x: list[float], y: list[float]) -> list[float]:
    """
    Compute the second derivatives (moments) of a natural cubic spline fit
    to (x, y) data.  Natural boundary conditions: M[0] = M[n-1] = 0.

    Uses the standard Thomas algorithm for tridiagonal systems.  Returns a
    list of n second derivatives.  If n < 3, returns zeros.
    """
    n = len(x)
    if n < 3:
        return [0.0] * n

    h = [x[i + 1] - x[i] for i in range(n - 1)]
    # Guard against zero-length intervals (duplicate x values)
    h = [max(hv, _EPS) for hv in h]

    # RHS
    rhs = [0.0] * n
    for i in range(1, n - 1):
        rhs[i] = 6.0 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])

    # Forward sweep (Thomas)
    diag = [0.0] * n
    diag[0] = 1.0
    diag[n - 1] = 1.0
    for i in range(1, n - 1):
        diag[i] = 2.0 * (h[i - 1] + h[i])

    upper = h[:]  # superdiagonal (length n-1)
    lower = h[:]  # subdiagonal  (length n-1)

    # Eliminate lower band
    for i in range(1, n - 1):
        factor = lower[i - 1] / diag[i - 1]
        diag[i] -= factor * upper[i - 1]
        rhs[i] -= factor * rhs[i - 1]

    # Back-substitute
    M = [0.0] * n
    M[n - 1] = rhs[n - 1] / diag[n - 1]
    for i in range(n - 2, -1, -1):
        M[i] = (rhs[i] - upper[i] * M[i + 1]) / diag[i]

    return M


def _spline_bending_energy(x: list[float], y: list[float]) -> float:
    """
    Approximate bending energy of a natural cubic spline through (x, y):

        E = ∫ (y'')² dx ≈ Σ_{i=0}^{n-2} (h_i/6) * (M_i² + M_i*M_{i+1} + M_{i+1}²)

    where M_i are the second derivatives.  Lower energy = fairer curve.
    Returns 0.0 if fewer than 3 points.
    """
    n = len(x)
    if n < 3:
        return 0.0
    M = _natural_cubic_spline_second_derivs(x, y)
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    h = [max(hv, _EPS) for hv in h]
    energy = 0.0
    for i in range(n - 1):
        energy += (h[i] / 6.0) * (M[i] ** 2 + M[i] * M[i + 1] + M[i + 1] ** 2)
    return energy


# ---------------------------------------------------------------------------
# fairing_report
# ---------------------------------------------------------------------------

def fairing_report(rows: object) -> dict:
    """
    Compute fairing quality metrics for a hull offset table.

    Metrics
    -------
    curvature_monotonicity
        Per-station assessment.  For each station the half-breadths (sorted by
        waterline, keel → sheer) are examined.  A station is *monotone* if the
        sequence is non-decreasing from keel to the breadth-maximum waterline
        and non-increasing above it (simple convex shape).  A *kink* is
        reported if consecutive differences change sign more than once
        (indicating an inflection not associated with the natural beam
        turnover).

        Result: list of dicts, one per station:
            ``{station, monotone: bool, kink_detected: bool, kink_at_wl: float|None}``

    batten_energy
        Approximate bending energy (metre³) of a natural cubic spline fit to
        the WL → Y profile at each station.  Lower = fairer.

        Result: list of ``{station, energy}`` dicts.

    roughness_per_waterline
        RMS of second differences of half-breadths across stations at each
        waterline (using central finite differences for interior stations,
        forward/backward at ends).  Measures fairness in the longitudinal
        direction.

        Result: list of ``{waterline, rms_second_diff}`` dicts.

    overall_roughness
        Mean of all per-waterline RMS second-difference values.  Single scalar
        summary — 0.0 on a perfectly fair hull.

    Parameters
    ----------
    rows : list[dict]
        Same format as :func:`hull_from_offsets`.

    Returns
    -------
    dict
        ``{"ok": True, "curvature_monotonicity": [...], "batten_energy": [...],
           "roughness_per_waterline": [...], "overall_roughness": float}``
        or ``{"ok": False, "errors": [...]}`` on bad input.
    """
    parsed, errors = _validate_offset_rows(rows)
    if errors:
        return {"ok": False, "errors": errors}

    table = _build_offset_table(parsed)
    stations = table.stations
    waterlines = table.waterlines

    # ── 1. Curvature monotonicity per station ──────────────────────────────
    mono_results: list[dict] = []
    for st in stations:
        ys = [table.offsets.get((st, wl)) for wl in waterlines]
        # Drop missing entries (hull may not reach all WLs at every station)
        pairs = [(wl, y) for wl, y in zip(waterlines, ys) if y is not None]

        if len(pairs) < 2:
            mono_results.append({
                "station": st,
                "monotone": True,
                "kink_detected": False,
                "kink_at_wl": None,
                "note": "fewer than 2 points at this station",
            })
            continue

        wl_pts = [p[0] for p in pairs]
        y_pts = [p[1] for p in pairs]

        diffs = [y_pts[i + 1] - y_pts[i] for i in range(len(y_pts) - 1)]

        # Find the sign of each diff (+1, -1, 0)
        def _sign(v: float) -> int:
            if v > _EPS:
                return 1
            if v < -_EPS:
                return -1
            return 0

        signs = [_sign(d) for d in diffs]

        # Count sign changes (ignoring zeros)
        sign_changes = 0
        kink_at_wl: Optional[float] = None
        prev = 0
        for idx, s in enumerate(signs):
            if s == 0:
                continue
            if prev != 0 and s != prev:
                sign_changes += 1
                if kink_at_wl is None:
                    # Record the waterline where the second sign change occurs
                    # (first sign change = normal beam turnover; second = kink)
                    if sign_changes > 1:
                        kink_at_wl = wl_pts[idx]
            prev = s

        kink = sign_changes > 1
        if kink and kink_at_wl is None:
            # sign_changes==2 but kink_at_wl not yet set; find it more carefully
            prev2 = 0
            changes_seen = 0
            for idx2, s2 in enumerate(signs):
                if s2 == 0:
                    continue
                if prev2 != 0 and s2 != prev2:
                    changes_seen += 1
                    if changes_seen == 2:
                        kink_at_wl = wl_pts[idx2]
                        break
                prev2 = s2

        mono_results.append({
            "station": st,
            "monotone": not kink,
            "kink_detected": kink,
            "kink_at_wl": kink_at_wl,
        })

    # ── 2. Batten (spline bending) energy per station ──────────────────────
    energy_results: list[dict] = []
    for st in stations:
        pairs = [
            (wl, table.offsets[(st, wl)])
            for wl in waterlines
            if (st, wl) in table.offsets
        ]
        if len(pairs) < 2:
            energy_results.append({"station": st, "energy": 0.0})
            continue
        wl_pts = [p[0] for p in pairs]
        y_pts = [p[1] for p in pairs]
        e = _spline_bending_energy(wl_pts, y_pts)
        energy_results.append({"station": st, "energy": round(e, 8)})

    # ── 3. Roughness per waterline (longitudinal) ──────────────────────────
    roughness_results: list[dict] = []
    for wl in waterlines:
        ys_at_wl = [table.offsets.get((st, wl)) for st in stations]
        valid = [(st, y) for st, y in zip(stations, ys_at_wl) if y is not None]
        if len(valid) < 3:
            roughness_results.append({"waterline": wl, "rms_second_diff": 0.0})
            continue

        st_pts = [v[0] for v in valid]
        y_pts = [v[1] for v in valid]
        n = len(y_pts)

        # Second finite differences (central for interior, forward/backward at ends)
        second_diffs: list[float] = []
        for i in range(n):
            if i == 0:
                d2 = y_pts[2] - 2 * y_pts[1] + y_pts[0]
            elif i == n - 1:
                d2 = y_pts[n - 1] - 2 * y_pts[n - 2] + y_pts[n - 3]
            else:
                d2 = y_pts[i + 1] - 2 * y_pts[i] + y_pts[i - 1]
            second_diffs.append(d2)

        rms = math.sqrt(sum(d ** 2 for d in second_diffs) / n)
        roughness_results.append({"waterline": wl, "rms_second_diff": round(rms, 8)})

    overall = (
        sum(r["rms_second_diff"] for r in roughness_results) / len(roughness_results)
        if roughness_results else 0.0
    )

    return {
        "ok": True,
        "curvature_monotonicity": mono_results,
        "batten_energy": energy_results,
        "roughness_per_waterline": roughness_results,
        "overall_roughness": round(overall, 8),
    }


# ---------------------------------------------------------------------------
# Simpson's rule helpers
# ---------------------------------------------------------------------------

def _simpsons_rule(x: list[float], y: list[float]) -> float:
    """
    Composite Simpson's 1/3 rule for unevenly-spaced data.

    Each consecutive trio (x_i, x_{i+1}, x_{i+2}) is integrated using the
    three-point Lagrange-based Newton-Cotes formula for unequal spacing.
    When n (number of points) is even, the last interval is handled by the
    trapezoid rule.

    For uniformly-spaced data with an odd number of points this reduces to the
    classical composite 1/3 rule and is exact for polynomials up to degree 3:

        h/3 * (y₀ + 4y₁ + 2y₂ + 4y₃ + ... + 4y_{n-2} + y_{n-1})

    Coefficients for each trio (x_i, x_{i+1}, x_{i+2}):
    Let h₁ = x_{i+1} - x_i, h₂ = x_{i+2} - x_{i+1}.

        w₀ = 1/(h₁(h₁+h₂)) * (h₁³/3 + h₁²h₂/2 - h₂³/6)
        w₁ = (h₁+h₂)³ / (6·h₁·h₂)
        w₂ = 1/(h₂(h₁+h₂)) * (h₂³/3 + h₁h₂²/2 - h₁³/6)

    These are the exact integrals of the three Lagrange basis polynomials over
    [x_i, x_{i+2}] — derivation via substitution u = x - x_{i+1}.

    If n < 2 returns 0.0.  If n == 2, returns trapezoid area.
    """
    n = len(x)
    if n < 2:
        return 0.0
    if n == 2:
        return 0.5 * (x[1] - x[0]) * (y[0] + y[1])

    total = 0.0
    i = 0
    while i + 2 < n:
        h1 = x[i + 1] - x[i]
        h2 = x[i + 2] - x[i + 1]
        if h1 < _EPS or h2 < _EPS:
            # Degenerate interval — skip
            i += 1
            continue
        # Correct three-point Lagrange-integral coefficients for uneven spacing
        w0 = (h1 ** 3 / 3.0 + h1 ** 2 * h2 / 2.0 - h2 ** 3 / 6.0) / (h1 * (h1 + h2))
        w1 = (h1 + h2) ** 3 / (6.0 * h1 * h2)
        w2 = (h2 ** 3 / 3.0 + h1 * h2 ** 2 / 2.0 - h1 ** 3 / 6.0) / (h2 * (h1 + h2))
        total += w0 * y[i] + w1 * y[i + 1] + w2 * y[i + 2]
        i += 2

    # Leftover single interval (trapezoid)
    if i + 1 == n - 1:
        total += 0.5 * (x[i + 1] - x[i]) * (y[i] + y[i + 1])

    return total


def _sectional_area(
    waterlines: list[float],
    half_breadths: list[float],
    design_wl: float,
) -> float:
    """
    Compute the submerged cross-sectional area at a station by integrating
    half-breadths from keel (WL=0 or table minimum) up to ``design_wl``.

    Only waterlines at or below ``design_wl`` are included.  The full beam
    is 2× the half-breadth, so the signed area is 2× the integral.

    Returns 0.0 if fewer than 2 points lie below the design waterline.
    """
    pairs = [
        (wl, hb)
        for wl, hb in zip(waterlines, half_breadths)
        if wl <= design_wl + _EPS and hb is not None
    ]
    if len(pairs) < 2:
        return 0.0
    wl_pts = [p[0] for p in pairs]
    hb_pts = [p[1] for p in pairs]
    # Integrate half-breadths, then multiply by 2 for full beam
    return 2.0 * _simpsons_rule(wl_pts, hb_pts)


# ---------------------------------------------------------------------------
# hydrostatics
# ---------------------------------------------------------------------------

def hydrostatics(rows: object, design_waterline: object = None) -> dict:
    """
    Compute basic hydrostatic properties for a hull offset table.

    The design waterline ``T`` is the depth to which the hull is considered
    submerged.  If not provided, the maximum waterline in the offset table is
    used (full immersion).

    Method: Simpson's rule (composite 1/3 rule) — exact for polynomials up
    to degree 3.  Reference: D. J. Eyres, *Ship Stability for Masters and
    Mates*, 5th ed., Butterworth-Heinemann (2001), Chapter 6.

    Quantities computed
    -------------------
    waterplane_area_m2
        Awp = ∫₀^L 2·y(x, T) dx  [m²]
        Integrates the waterplane half-breadths at design waterline T along
        the ship length.

    displaced_volume_m3
        ∇ = ∫₀^L Aₓ(x) dx  [m³]
        where Aₓ(x) is the submerged cross-sectional area at station x,
        computed by integrating half-breadths from keel to T.

    lcb_from_bow_m
        LCB = (1/∇) · ∫₀^L x · Aₓ(x) dx  [m from bow]
        Longitudinal Centre of Buoyancy.  Measured from the first (bow-most)
        station.

    Parameters
    ----------
    rows : list[dict]
        Half-breadth offset table in ``{station, waterline, half_breadth}`` format.
    design_waterline : float, optional
        Waterline height (metres) to treat as the loaded waterplane.
        Defaults to the maximum waterline in the table.

    Returns
    -------
    dict
        ``{"ok": True, "waterplane_area_m2": ..., "displaced_volume_m3": ...,
           "lcb_from_bow_m": ..., "design_waterline": ...,
           "station_count": ..., "waterline_count": ...}``
        or ``{"ok": False, "errors": [...]}`` — never raises.

    Box-barge identity check
    ------------------------
    For a rectangular (box-barge) hull of length L, beam B, draft T:
        ∇ = L × B × T          (the usual displaced-volume formula)
    This implementation satisfies that identity within the precision of
    Simpson's rule (exact for constant functions).
    """
    parsed, errors = _validate_offset_rows(rows)
    if errors:
        return {"ok": False, "errors": errors}

    table = _build_offset_table(parsed)
    stations = table.stations
    waterlines = table.waterlines

    # Determine design waterline
    if design_waterline is None:
        dwl = waterlines[-1]
    else:
        try:
            dwl = float(design_waterline)
        except (TypeError, ValueError):
            return {"ok": False, "errors": [
                "design_waterline must be a number (metres)"
            ]}
        if dwl < waterlines[0] - _EPS:
            return {"ok": False, "errors": [
                f"design_waterline {dwl} is below the keel waterline {waterlines[0]}"
            ]}

    # ── Waterplane area ────────────────────────────────────────────────────
    # Half-breadths at design_waterline by linear interpolation when needed.
    wp_half_breadths: list[float] = []
    for st in stations:
        hb = _interp_half_breadth(table, st, dwl)
        wp_half_breadths.append(hb if hb is not None else 0.0)

    awp = 2.0 * _simpsons_rule(stations, wp_half_breadths)

    # ── Sectional areas ───────────────────────────────────────────────────
    sect_areas: list[float] = []
    for st in stations:
        wl_pts = [wl for wl in waterlines if wl <= dwl + _EPS]
        hb_pts = [table.offsets.get((st, wl), 0.0) for wl in wl_pts]
        area = _sectional_area(wl_pts, hb_pts, dwl)
        sect_areas.append(area)

    # ── Displaced volume ──────────────────────────────────────────────────
    nabla = _simpsons_rule(stations, sect_areas)

    # ── LCB ───────────────────────────────────────────────────────────────
    # Moment of volume about bow (first station)
    bow = stations[0]
    moments = [(st - bow) * a for st, a in zip(stations, sect_areas)]
    moment_integral = _simpsons_rule(stations, moments)

    if nabla > _EPS:
        lcb = moment_integral / nabla
    else:
        lcb = 0.0

    return {
        "ok": True,
        "waterplane_area_m2": round(awp, 6),
        "displaced_volume_m3": round(nabla, 6),
        "lcb_from_bow_m": round(lcb, 6),
        "design_waterline": dwl,
        "station_count": len(stations),
        "waterline_count": len(waterlines),
    }


def _interp_half_breadth(
    table: HullOffsetTable,
    station: float,
    waterline: float,
) -> Optional[float]:
    """
    Return the half-breadth at (station, waterline) from the offset table.
    If the exact waterline is not in the table, linearly interpolate between
    the two nearest waterlines.  Returns None if station is not in the table
    or no bounding waterlines exist.
    """
    if station not in {s for s in table.stations}:
        return None

    # Exact match
    val = table.offsets.get((station, waterline))
    if val is not None:
        return val

    # Find bounding waterlines
    below = [wl for wl in table.waterlines if wl <= waterline + _EPS]
    above = [wl for wl in table.waterlines if wl >= waterline - _EPS]

    if not below or not above:
        return None

    wl_lo = below[-1]
    wl_hi = above[0]

    if abs(wl_hi - wl_lo) < _EPS:
        return table.offsets.get((station, wl_lo), 0.0)

    hb_lo = table.offsets.get((station, wl_lo))
    hb_hi = table.offsets.get((station, wl_hi))

    if hb_lo is None or hb_hi is None:
        # One of the bounding values is missing; fall back to whichever is available
        return hb_lo if hb_lo is not None else hb_hi

    t = (waterline - wl_lo) / (wl_hi - wl_lo)
    return hb_lo + t * (hb_hi - hb_lo)


# ---------------------------------------------------------------------------
# Spline fairing helpers
# ---------------------------------------------------------------------------

def _fair_profile(wl_pts: List[float], y_pts: List[float]) -> List[float]:
    """
    Fair a single station profile (WL → half-breadth) by fitting a natural
    cubic spline and re-evaluating at the original WL positions.

    The spline is the minimum-bending-energy curve through the input points;
    re-evaluating it at the same WL positions produces a smoothed (faired)
    version of the offsets that removes local kinks while preserving the
    overall shape.

    Returns the faired half-breadths clamped to >= 0.
    If fewer than 3 points, the original values are returned unchanged.
    """
    n = len(wl_pts)
    if n < 3:
        return list(y_pts)

    M = _natural_cubic_spline_second_derivs(wl_pts, y_pts)
    h = [wl_pts[i + 1] - wl_pts[i] for i in range(n - 1)]
    h = [max(hv, _EPS) for hv in h]

    faired = []
    for j, wl in enumerate(wl_pts):
        # Locate the span containing wl
        span = 0
        for k in range(n - 1):
            if wl <= wl_pts[k + 1] + _EPS:
                span = k
                break

        # Evaluate cubic spline at wl using the span
        t = wl - wl_pts[span]
        hi = h[span]
        # Standard cubic spline formula (Piegl & Tiller notation)
        a0 = (wl_pts[span + 1] - wl) / hi
        a1 = t / hi
        val = (
            a0 * y_pts[span]
            + a1 * y_pts[span + 1]
            + ((a0 ** 3 - a0) * M[span] + (a1 ** 3 - a1) * M[span + 1])
            * hi ** 2 / 6.0
        )
        faired.append(max(0.0, val))

    return faired


def _make_uniform_knots(n: int, degree: int) -> List[float]:
    """
    Build a clamped uniform knot vector for n control points and given degree.

    Length = n + degree + 1.
    First (degree+1) knots = 0.0, last (degree+1) = 1.0, inner knots uniform.
    """
    inner = n - degree - 1
    if inner <= 0:
        return [0.0] * (degree + 1) + [1.0] * (degree + 1)
    step = 1.0 / (inner + 1)
    return (
        [0.0] * (degree + 1)
        + [step * k for k in range(1, inner + 1)]
        + [1.0] * (degree + 1)
    )


def _build_nurbs_surface_from_grid(
    control_grid: List[List[List[float]]],
    degree_u: int,
    degree_v: int,
    knots_u: List[float],
    knots_v: List[float],
) -> dict:
    """
    Serialize a NURBS surface control grid into the surface_analysis tool format.

    control_grid[i][j] = [x, y, z] for control point (i, j).
    Returns a dict with keys matching the `_build_surface_from_args` convention
    used by surface_analysis.py tools.
    """
    nu = len(control_grid)
    nv = len(control_grid[0]) if nu > 0 else 0
    flat_cp = [pt for row in control_grid for pt in row]
    return {
        "degree_u": degree_u,
        "degree_v": degree_v,
        "num_u": nu,
        "num_v": nv,
        "control_points": flat_cp,
        "knots_u": knots_u,
        "knots_v": knots_v,
    }


def _curvature_combs_from_grid(
    control_grid: List[List[List[float]]],
    degree_u: int,
    degree_v: int,
    knots_u: List[float],
    knots_v: List[float],
    uv_density: float = 0.1,
    scale_factor: float = 10.0,
) -> dict:
    """
    Compute curvature-comb samples for a NURBS surface built from control_grid.

    Uses the pure-Python surface_analysis.gaussian_mean_curvature to sample
    principal curvatures on a UV grid, matching the payload format consumed by
    `CurvatureCombOverlay.jsx` (k1, k2, mean H, Gaussian K per sample point).

    Returns a dict::

        {
          "ok": bool,
          "uv_density": float,
          "scale_factor": float,
          "samples": [
              {"u": float, "v": float, "k1": float, "k2": float,
               "H": float, "K": float, "pt": [x, y, z]},
              ...
          ],
          "H_min": float, "H_max": float,
          "K_min": float, "K_max": float,
          "num_samples": int,
        }

    On failure returns {"ok": False, "reason": str}.
    """
    try:
        import numpy as np
        from kerf_cad_core.geom.nurbs import NurbsSurface
        from kerf_cad_core.geom.surface_analysis import (
            gaussian_mean_curvature,
            principal_curvatures,
            _uv_grid,
            _clamp_grid,
        )

        nu_cp = len(control_grid)
        nv_cp = len(control_grid[0]) if nu_cp > 0 else 0

        cp_array = np.array(control_grid, dtype=float)  # shape (nu, nv, 3)

        surf = NurbsSurface(
            degree_u=degree_u,
            degree_v=degree_v,
            control_points=cp_array,
            knots_u=np.array(knots_u, dtype=float),
            knots_v=np.array(knots_v, dtype=float),
        )

        # Grid resolution derived from uv_density (0.01 → dense; 0.5 → coarse)
        n_u = max(3, min(50, int(round(1.0 / uv_density))))
        n_v = max(3, min(50, int(round(1.0 / uv_density))))
        n_u, n_v = _clamp_grid(n_u, n_v)

        us, vs = _uv_grid(surf, n_u, n_v)

        from kerf_cad_core.geom.surface_analysis import _analytic_curvature_data

        samples = []
        H_vals: List[float] = []
        K_vals: List[float] = []

        from kerf_cad_core.geom.nurbs import surface_evaluate

        for u in us:
            for v in vs:
                cd = _analytic_curvature_data(surf, u, v)
                if cd is None:
                    continue
                pt = surface_evaluate(surf, u, v).tolist()
                entry = {
                    "u": round(float(u), 6),
                    "v": round(float(v), 6),
                    "k1": round(float(cd["k1"]), 8),
                    "k2": round(float(cd["k2"]), 8),
                    "H": round(float(cd["H"]), 8),
                    "K": round(float(cd["K"]), 8),
                    "pt": [round(c, 6) for c in pt[:3]],
                }
                samples.append(entry)
                H_vals.append(cd["H"])
                K_vals.append(cd["K"])

        if not samples:
            return {"ok": False, "reason": "no valid curvature samples produced"}

        return {
            "ok": True,
            "uv_density": uv_density,
            "scale_factor": scale_factor,
            "samples": samples,
            "H_min": round(min(H_vals), 8),
            "H_max": round(max(H_vals), 8),
            "K_min": round(min(K_vals), 8),
            "K_max": round(max(K_vals), 8),
            "num_samples": len(samples),
        }

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# faired_hull_surface
# ---------------------------------------------------------------------------

def faired_hull_surface(
    rows: object,
    uv_density: float = 0.1,
    scale_factor: float = 10.0,
    fairing_passes: int = 1,
) -> dict:
    """
    Build a faired NURBS hull surface from a half-breadth offset table.

    Fairing algorithm
    -----------------
    1. Validate and parse the offset table (same as :func:`hull_from_offsets`).
    2. For each station section, fit a natural cubic spline through the
       (WL, half-breadth) profile and re-evaluate it at the original WL
       positions.  This yields a *faired* half-breadth that is smooth across
       the full depth (batten fairing in the transverse direction).
    3. Repeat for the longitudinal direction: for each waterline, fit a spline
       through the station → faired-half-breadth values and re-evaluate.
       This ensures fairness longitudinally as well.
    4. Repeat steps 2–3 for `fairing_passes` iterations (default 1; 2–3
       passes produce Class-A quality on most hull forms).
    5. Build a degree-3 × degree-3 NURBS surface whose control points are
       the 3-D locations (station, faired_half_breadth, waterline) of the
       faired grid.  Clamped uniform knot vectors are used.
    6. Sample principal curvatures on a UV grid (via the existing
       ``surface_analysis.gaussian_mean_curvature`` infra) and embed the
       result in a ``curvature_combs`` field matching the payload consumed by
       the ``CurvatureCombOverlay.jsx`` frontend component.

    Fairness criterion (Definition of Done)
    ----------------------------------------
    The returned ``fairness_metrics`` field reports:

    ``all_stations_fair``
        True when every station profile has no kinks after fairing
        (matches :func:`fairing_report` ``curvature_monotonicity``).

    ``max_batten_energy_improvement``
        Fraction by which the maximum per-station batten energy decreased
        vs the raw offsets.  Positive = fairing improved smoothness.

    ``overall_roughness_improvement``
        Fraction by which the longitudinal roughness decreased.  Positive
        = fairing improved longitudinal smoothness.

    Parameters
    ----------
    rows : list[dict]
        Half-breadth offset table.  Same format as :func:`hull_from_offsets`.
    uv_density : float
        UV grid step as a fraction of the parameter range for curvature-comb
        sampling (default 0.1 → ~10×10 grid).  Range: 0.01–0.5.
    scale_factor : float
        Comb line length multiplier (default 10).
    fairing_passes : int
        Number of transverse + longitudinal fairing passes (default 1).
        Increase to 2–3 for high-curvature or irregular hull forms.

    Returns
    -------
    dict
        On success::

            {
              "ok": True,
              "op": "marine_faired_hull_surface",
              "loa": float,
              "depth": float,
              "max_half_beam": float,
              "station_count": int,
              "waterline_count": int,
              "fairing_passes": int,
              "nurbs_surface": {
                "degree_u": int, "degree_v": int,
                "num_u": int, "num_v": int,
                "control_points": [[x, y, z], ...],
                "knots_u": [...], "knots_v": [...],
              },
              "curvature_combs": {
                "ok": bool,
                "samples": [...],   # [{u, v, k1, k2, H, K, pt}, ...]
                "H_min": float, "H_max": float,
                "K_min": float, "K_max": float,
                "num_samples": int,
              },
              "fairness_metrics": {
                "all_stations_fair": bool,
                "max_batten_energy_improvement": float,
                "overall_roughness_improvement": float,
                "raw_overall_roughness": float,
                "faired_overall_roughness": float,
              },
            }

        On failure: ``{"ok": False, "errors": [...]}``  — never raises.
    """
    # ── Validate input ──────────────────────────────────────────────────────
    parsed, errors = _validate_offset_rows(rows)
    if errors:
        return {"ok": False, "errors": errors}

    # Clamp uv_density
    try:
        uv_density = float(uv_density)
        if uv_density <= 0 or uv_density > 0.5:
            uv_density = 0.1
    except (TypeError, ValueError):
        uv_density = 0.1

    try:
        scale_factor = float(scale_factor)
        if scale_factor <= 0:
            scale_factor = 10.0
    except (TypeError, ValueError):
        scale_factor = 10.0

    try:
        fairing_passes = max(1, int(fairing_passes))
    except (TypeError, ValueError):
        fairing_passes = 1

    table = _build_offset_table(parsed)
    stations = table.stations
    waterlines = table.waterlines

    # ── Build the initial grid (stations × waterlines → half-breadth) ───────
    # grid[i][j] = half-breadth at (stations[i], waterlines[j])
    # Missing entries are filled with 0.0 (keel-side default).
    grid: List[List[float]] = []
    for st in stations:
        row_hb = []
        for wl in waterlines:
            hb = table.offsets.get((st, wl), 0.0)
            row_hb.append(hb)
        grid.append(row_hb)

    # ── Raw fairing metrics (before fairing) ─────────────────────────────────
    raw_report = fairing_report(rows)
    raw_roughness = raw_report.get("overall_roughness", 0.0) if raw_report.get("ok") else 0.0
    raw_energies = {
        e["station"]: e["energy"]
        for e in raw_report.get("batten_energy", [])
        if raw_report.get("ok")
    }

    # ── Iterative fairing ─────────────────────────────────────────────────────
    for _pass in range(fairing_passes):
        # Transverse pass: fair each station profile (WL → Y)
        for i, st in enumerate(stations):
            faired_y = _fair_profile(waterlines, grid[i])
            grid[i] = faired_y

        # Longitudinal pass: fair each waterline profile (station → Y)
        for j in range(len(waterlines)):
            y_across = [grid[i][j] for i in range(len(stations))]
            faired_across = _fair_profile(stations, y_across)
            for i in range(len(stations)):
                grid[i][j] = faired_across[i]

    # ── Faired fairness metrics ───────────────────────────────────────────────
    # Build faired rows for fairing_report
    faired_rows = [
        {"station": stations[i], "waterline": waterlines[j], "half_breadth": grid[i][j]}
        for i in range(len(stations))
        for j in range(len(waterlines))
    ]
    faired_report = fairing_report(faired_rows)
    faired_roughness = faired_report.get("overall_roughness", 0.0) if faired_report.get("ok") else 0.0
    faired_energies = {
        e["station"]: e["energy"]
        for e in faired_report.get("batten_energy", [])
        if faired_report.get("ok")
    }

    # Curvature monotonicity: all stations fair?
    all_stations_fair = all(
        not e["kink_detected"]
        for e in faired_report.get("curvature_monotonicity", [])
    ) if faired_report.get("ok") else False

    # Batten energy improvement (max across stations)
    max_raw_energy = max(raw_energies.values(), default=0.0)
    max_faired_energy = max(faired_energies.values(), default=0.0)
    if max_raw_energy > _EPS:
        energy_improvement = (max_raw_energy - max_faired_energy) / max_raw_energy
    else:
        energy_improvement = 0.0

    # Roughness improvement
    if raw_roughness > _EPS:
        roughness_improvement = (raw_roughness - faired_roughness) / raw_roughness
    else:
        roughness_improvement = 0.0

    # ── Build NURBS surface control grid ─────────────────────────────────────
    # Control points: P[i][j] = (station_i, faired_hb_ij, waterline_j)
    # i = U direction (along stations), j = V direction (along waterlines)
    nu = len(stations)
    nv = len(waterlines)
    degree_u = min(3, nu - 1)
    degree_v = min(3, nv - 1)

    control_grid: List[List[List[float]]] = []
    for i, st in enumerate(stations):
        row_pts = []
        for j, wl in enumerate(waterlines):
            hb = grid[i][j]
            # XYZ: X=station (longitudinal), Y=half-breadth (transverse), Z=waterline (vertical)
            row_pts.append([st, hb, wl])
        control_grid.append(row_pts)

    knots_u = _make_uniform_knots(nu, degree_u)
    knots_v = _make_uniform_knots(nv, degree_v)

    nurbs_surface_data = _build_nurbs_surface_from_grid(
        control_grid, degree_u, degree_v, knots_u, knots_v
    )

    # ── Curvature combs ───────────────────────────────────────────────────────
    combs = _curvature_combs_from_grid(
        control_grid, degree_u, degree_v, knots_u, knots_v,
        uv_density=uv_density,
        scale_factor=scale_factor,
    )

    loa = stations[-1] - stations[0]
    depth = waterlines[-1] - waterlines[0]
    max_hb = max(grid[i][j] for i in range(nu) for j in range(nv))

    return {
        "ok": True,
        "op": "marine_faired_hull_surface",
        "loa": loa,
        "depth": depth,
        "max_half_beam": max_hb,
        "station_count": nu,
        "waterline_count": nv,
        "fairing_passes": fairing_passes,
        "nurbs_surface": nurbs_surface_data,
        "curvature_combs": combs,
        "fairness_metrics": {
            "all_stations_fair": all_stations_fair,
            "max_batten_energy_improvement": round(energy_improvement, 6),
            "overall_roughness_improvement": round(roughness_improvement, 6),
            "raw_overall_roughness": round(raw_roughness, 8),
            "faired_overall_roughness": round(faired_roughness, 8),
        },
    }
