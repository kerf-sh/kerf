"""
kerf_cad_core.surveying.cogo — Pure-Python COGO / traverse / area computations.

Public functions
----------------
  dms_to_dd(degrees, minutes, seconds) → decimal degrees
  dd_to_dms(dd) → (degrees, minutes, seconds)
  bearing_to_azimuth(quadrant, dd) → azimuth degrees
  azimuth_to_bearing(azimuth_dd) → (quadrant, dd)
  forward(northing, easting, azimuth_dd, distance) → (N, E)
  inverse(n1, e1, n2, e2) → (azimuth_dd, distance)
  traverse_misclosure(legs) → misclosure report dict
  traverse_adjust(legs, method) → adjusted traverse dict
  area_by_coordinates(points) → area (m²)
  area_by_dmd(points) → area (m²)  [double meridian distance method]
  line_line_intersection(p1, p2, p3, p4) → (N, E) or None
  line_circle_intersection(p1, p2, centre, radius) → list[(N, E)]
  point_of_intersection(az1, n1, e1, az2, n2, e2) → (N, E)
  resection(p_known, obs_angles) → (N, E)
  level_loop_adjust(observations, known_elev) → adjusted list

All functions return plain dicts:
    success → {"ok": True, ...}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise; traverse precision warnings are issued via the
``warnings`` module (never exceptions).

Units
-----
  Coordinates  — metres (N northing, E easting)
  Distances    — metres
  Angles       — decimal degrees or DMS tuples as noted
  Areas        — square metres (m²)

References
----------
Wolf & Ghilani, "Elementary Surveying", 14th ed.
Bannister, Raymond, Baker, "Surveying", 7th ed.
BLM "Manual of Surveying Instructions", 2009.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TWO_PI = 2.0 * math.pi
_DEFAULT_TRAVERSE_TOLERANCE = 1.0 / 5000.0  # 1:5000 precision ratio


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def _rad_to_deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def _normalise_azimuth(az_deg: float) -> float:
    """Normalise azimuth to [0, 360)."""
    az = az_deg % 360.0
    if az < 0.0:
        az += 360.0
    return az


# ---------------------------------------------------------------------------
# 1. DMS ↔ Decimal Degrees
# ---------------------------------------------------------------------------

def dms_to_dd(degrees: float, minutes: float, seconds: float) -> dict:
    """
    Convert degrees-minutes-seconds to decimal degrees.

    Parameters
    ----------
    degrees : float  — integer part of angle (may be negative for S/W)
    minutes : float  — must be in [0, 60)
    seconds : float  — must be in [0, 60)

    Returns
    -------
    {"ok": True, "dd": decimal_degrees}
    """
    for name, val in (("degrees", degrees), ("minutes", minutes), ("seconds", seconds)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    d = float(degrees)
    m = float(minutes)
    s = float(seconds)

    if not (0.0 <= m < 60.0):
        return _err(f"minutes must be in [0, 60), got {m}")
    if not (0.0 <= s < 60.0):
        return _err(f"seconds must be in [0, 60), got {s}")

    sign = -1.0 if d < 0.0 else 1.0
    dd = sign * (abs(d) + m / 60.0 + s / 3600.0)
    return {"ok": True, "dd": dd}


def dd_to_dms(dd: float) -> dict:
    """
    Convert decimal degrees to degrees-minutes-seconds.

    Returns
    -------
    {"ok": True, "degrees": int, "minutes": int, "seconds": float}
    """
    err = _guard_finite("dd", dd)
    if err:
        return _err(err)

    dd_val = float(dd)
    sign = -1 if dd_val < 0 else 1
    total_seconds = abs(dd_val) * 3600.0
    deg = int(total_seconds // 3600)
    rem = total_seconds - deg * 3600.0
    mins = int(rem // 60)
    secs = rem - mins * 60.0

    return {
        "ok": True,
        "degrees": sign * deg,
        "minutes": mins,
        "seconds": round(secs, 6),
    }


# ---------------------------------------------------------------------------
# 2. Bearing ↔ Azimuth conversion
# ---------------------------------------------------------------------------

# Bearing quadrant convention: "N45E" → quadrant="NE", bearing_dd=45.0
_VALID_QUADRANTS = {"NE", "SE", "SW", "NW"}


def bearing_to_azimuth(quadrant: str, bearing_dd: float) -> dict:
    """
    Convert a reduced bearing (quadrant + angle) to a whole-circle azimuth.

    Parameters
    ----------
    quadrant : str   — "NE", "SE", "SW", or "NW"
    bearing_dd : float — bearing angle from N or S axis in decimal degrees;
                         must be in (0, 90]

    Returns
    -------
    {"ok": True, "azimuth_dd": azimuth in [0, 360)}

    Notes
    -----
    NE quadrant: azimuth = bearing_dd
    SE quadrant: azimuth = 180 - bearing_dd
    SW quadrant: azimuth = 180 + bearing_dd
    NW quadrant: azimuth = 360 - bearing_dd
    """
    err = _guard_finite("bearing_dd", bearing_dd)
    if err:
        return _err(err)

    q = str(quadrant).strip().upper()
    if q not in _VALID_QUADRANTS:
        return _err(f"quadrant must be one of {sorted(_VALID_QUADRANTS)}, got {quadrant!r}")

    b = float(bearing_dd)
    if not (0.0 < b <= 90.0):
        return _err(f"bearing_dd must be in (0, 90], got {b}")

    if q == "NE":
        az = b
    elif q == "SE":
        az = 180.0 - b
    elif q == "SW":
        az = 180.0 + b
    else:  # NW
        az = 360.0 - b

    return {"ok": True, "azimuth_dd": _normalise_azimuth(az)}


def azimuth_to_bearing(azimuth_dd: float) -> dict:
    """
    Convert a whole-circle azimuth to a reduced bearing.

    Parameters
    ----------
    azimuth_dd : float — azimuth in [0, 360)

    Returns
    -------
    {"ok": True, "quadrant": str, "bearing_dd": float, "bearing_str": str}
    bearing_str format: e.g. "N45°30'00\"E"
    """
    err = _guard_finite("azimuth_dd", azimuth_dd)
    if err:
        return _err(err)

    az = _normalise_azimuth(float(azimuth_dd))

    if az <= 90.0:
        q = "NE"
        b = az
    elif az <= 180.0:
        q = "SE"
        b = 180.0 - az
    elif az <= 270.0:
        q = "SW"
        b = az - 180.0
    else:
        q = "NW"
        b = 360.0 - az

    dms = dd_to_dms(b)
    bearing_str = (
        f"{q[0]}{abs(dms['degrees'])}°{dms['minutes']:02d}'{dms['seconds']:05.2f}\"{q[1]}"
    )

    return {
        "ok": True,
        "quadrant": q,
        "bearing_dd": b,
        "bearing_str": bearing_str,
        "azimuth_dd": az,
    }


# ---------------------------------------------------------------------------
# 3. Forward problem: point from point + azimuth + distance
# ---------------------------------------------------------------------------

def forward(
    northing: float,
    easting: float,
    azimuth_dd: float,
    distance: float,
) -> dict:
    """
    Compute the coordinates of a new point from a known point, azimuth, and
    distance (polar → rectangular conversion).

    Parameters
    ----------
    northing   : float — starting point northing (m)
    easting    : float — starting point easting (m)
    azimuth_dd : float — whole-circle azimuth (decimal degrees)
    distance   : float — horizontal distance (m); must be >= 0

    Returns
    -------
    {"ok": True, "northing": N2, "easting": E2,
     "delta_N": dN, "delta_E": dE}
    """
    for name, val in (("northing", northing), ("easting", easting),
                      ("azimuth_dd", azimuth_dd)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("distance", distance)
    if err:
        return _err(err)

    az_rad = _deg_to_rad(_normalise_azimuth(float(azimuth_dd)))
    d = float(distance)

    dN = d * math.cos(az_rad)
    dE = d * math.sin(az_rad)

    return {
        "ok": True,
        "northing": float(northing) + dN,
        "easting": float(easting) + dE,
        "delta_N": dN,
        "delta_E": dE,
        "azimuth_dd": _normalise_azimuth(float(azimuth_dd)),
        "distance": d,
    }


# ---------------------------------------------------------------------------
# 4. Inverse problem: azimuth + distance between two points
# ---------------------------------------------------------------------------

def inverse(
    n1: float,
    e1: float,
    n2: float,
    e2: float,
) -> dict:
    """
    Compute the azimuth and horizontal distance from point 1 to point 2
    (rectangular → polar conversion).

    Parameters
    ----------
    n1, e1 : float — coordinates of from-point (m)
    n2, e2 : float — coordinates of to-point (m)

    Returns
    -------
    {"ok": True, "azimuth_dd": az, "distance": d,
     "delta_N": dN, "delta_E": dE,
     "quadrant": q, "bearing_dd": b}
    """
    for name, val in (("n1", n1), ("e1", e1), ("n2", n2), ("e2", e2)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    dN = float(n2) - float(n1)
    dE = float(e2) - float(e1)
    dist = math.hypot(dN, dE)

    if dist == 0.0:
        return _err("Points are coincident; azimuth is undefined.")

    az_rad = math.atan2(dE, dN)
    az_deg = _normalise_azimuth(_rad_to_deg(az_rad))

    bearing_result = azimuth_to_bearing(az_deg)

    return {
        "ok": True,
        "azimuth_dd": az_deg,
        "distance": dist,
        "delta_N": dN,
        "delta_E": dE,
        "quadrant": bearing_result.get("quadrant"),
        "bearing_dd": bearing_result.get("bearing_dd"),
        "bearing_str": bearing_result.get("bearing_str"),
    }


# ---------------------------------------------------------------------------
# 5. Traverse misclosure and adjustment
# ---------------------------------------------------------------------------

def traverse_misclosure(
    legs: list[dict],
    *,
    tolerance: float = _DEFAULT_TRAVERSE_TOLERANCE,
) -> dict:
    """
    Compute closed-traverse misclosure (linear and angular).

    Parameters
    ----------
    legs : list of dicts, each with:
        "azimuth_dd"  : float — measured azimuth of leg (decimal degrees)
        "distance"    : float — horizontal distance of leg (m)
    tolerance : float — acceptable precision ratio (default 1:5000 = 0.0002)
                        A warning is issued (not an exception) if the precision
                        is worse than this ratio.

    Returns
    -------
    {"ok": True,
     "closure_N": total northing misclosure (m),
     "closure_E": total easting misclosure (m),
     "linear_misclosure": linear distance of misclosure (m),
     "traverse_length": total traverse distance (m),
     "precision_ratio": 1/K where K = traverse_length/linear_misclosure,
     "precision_ok": bool,
     "legs": list of computed leg dicts with delta_N, delta_E}
    """
    if not legs:
        return _err("legs must not be empty")

    sum_N = 0.0
    sum_E = 0.0
    total_dist = 0.0
    leg_results = []

    for i, leg in enumerate(legs):
        az = leg.get("azimuth_dd")
        dist = leg.get("distance")
        if az is None:
            return _err(f"legs[{i}] missing 'azimuth_dd'")
        if dist is None:
            return _err(f"legs[{i}] missing 'distance'")

        err = _guard_finite(f"legs[{i}].azimuth_dd", az)
        if err:
            return _err(err)
        err = _guard_nonneg(f"legs[{i}].distance", dist)
        if err:
            return _err(err)

        az_rad = _deg_to_rad(_normalise_azimuth(float(az)))
        d = float(dist)
        dN = d * math.cos(az_rad)
        dE = d * math.sin(az_rad)

        sum_N += dN
        sum_E += dE
        total_dist += d

        leg_results.append({
            "azimuth_dd": _normalise_azimuth(float(az)),
            "distance": d,
            "delta_N": dN,
            "delta_E": dE,
        })

    linear_misc = math.hypot(sum_N, sum_E)

    if total_dist > 0.0 and linear_misc > 0.0:
        precision_ratio = linear_misc / total_dist
    elif linear_misc == 0.0:
        precision_ratio = 0.0
    else:
        precision_ratio = float("inf")

    precision_ok = precision_ratio <= tolerance

    if not precision_ok:
        warnings.warn(
            f"Traverse precision {1.0/precision_ratio:.0f}:1 is worse than "
            f"required {1.0/tolerance:.0f}:1 "
            f"(misclosure={linear_misc:.4f} m over {total_dist:.4f} m).",
            UserWarning,
            stacklevel=2,
        )

    return {
        "ok": True,
        "closure_N": sum_N,
        "closure_E": sum_E,
        "linear_misclosure": linear_misc,
        "traverse_length": total_dist,
        "precision_ratio": precision_ratio,
        "precision_ok": precision_ok,
        "legs": leg_results,
    }


def traverse_adjust(
    legs: list[dict],
    *,
    method: str = "compass",
    tolerance: float = _DEFAULT_TRAVERSE_TOLERANCE,
) -> dict:
    """
    Adjust a closed traverse using Compass (Bowditch) or Transit rule.

    Parameters
    ----------
    legs : list of dicts (same schema as traverse_misclosure)
    method : str
        "compass" (default) — Compass/Bowditch rule:
            correction_N[i] = -closure_N × (dist[i] / total_dist)
            correction_E[i] = -closure_E × (dist[i] / total_dist)
        "transit" — Transit rule:
            correction_N[i] = -closure_N × |dN[i]| / sum(|dN|)
            correction_E[i] = -closure_E × |dE[i]| / sum(|dE|)
    tolerance : float — passed through to traverse_misclosure

    Returns
    -------
    {"ok": True,
     "method": str,
     "adjusted_legs": list of leg dicts with corrected delta_N, delta_E,
     "stations": list of cumulative adjusted coordinates starting from (0,0),
     "closure_before": linear misclosure before adjustment (m),
     "closure_after": linear misclosure after adjustment (m, should be ~0)}
    """
    m = str(method).strip().lower()
    if m not in ("compass", "transit"):
        return _err(f"method must be 'compass' or 'transit', got {method!r}")

    misc = traverse_misclosure(legs, tolerance=tolerance)
    if not misc["ok"]:
        return misc

    closure_N = misc["closure_N"]
    closure_E = misc["closure_E"]
    total_dist = misc["traverse_length"]
    raw_legs = misc["legs"]

    if total_dist == 0.0:
        return _err("Total traverse length is zero.")

    adjusted_legs = []

    if m == "compass":
        for leg in raw_legs:
            d = leg["distance"]
            corr_N = -closure_N * (d / total_dist)
            corr_E = -closure_E * (d / total_dist)
            adjusted_legs.append({
                "azimuth_dd": leg["azimuth_dd"],
                "distance": d,
                "delta_N": leg["delta_N"] + corr_N,
                "delta_E": leg["delta_E"] + corr_E,
                "correction_N": corr_N,
                "correction_E": corr_E,
            })
    else:  # transit
        sum_abs_dN = sum(abs(leg["delta_N"]) for leg in raw_legs)
        sum_abs_dE = sum(abs(leg["delta_E"]) for leg in raw_legs)
        for leg in raw_legs:
            if sum_abs_dN > 0.0:
                corr_N = -closure_N * abs(leg["delta_N"]) / sum_abs_dN
            else:
                corr_N = 0.0
            if sum_abs_dE > 0.0:
                corr_E = -closure_E * abs(leg["delta_E"]) / sum_abs_dE
            else:
                corr_E = 0.0
            adjusted_legs.append({
                "azimuth_dd": leg["azimuth_dd"],
                "distance": leg["distance"],
                "delta_N": leg["delta_N"] + corr_N,
                "delta_E": leg["delta_E"] + corr_E,
                "correction_N": corr_N,
                "correction_E": corr_E,
            })

    # Compute cumulative station coordinates (starting at origin)
    stations = [{"northing": 0.0, "easting": 0.0}]
    n, e = 0.0, 0.0
    for leg in adjusted_legs:
        n += leg["delta_N"]
        e += leg["delta_E"]
        stations.append({"northing": n, "easting": e})

    # Closure after adjustment (should be near zero)
    final_N = sum(lg["delta_N"] for lg in adjusted_legs)
    final_E = sum(lg["delta_E"] for lg in adjusted_legs)
    closure_after = math.hypot(final_N, final_E)

    return {
        "ok": True,
        "method": m,
        "adjusted_legs": adjusted_legs,
        "stations": stations,
        "closure_before": misc["linear_misclosure"],
        "closure_after": closure_after,
        "precision_ratio_before": misc["precision_ratio"],
        "precision_ok_before": misc["precision_ok"],
    }


# ---------------------------------------------------------------------------
# 6. Area by coordinates (Shoelace / Gauss formula)
# ---------------------------------------------------------------------------

def area_by_coordinates(points: list[dict]) -> dict:
    """
    Compute the area enclosed by a polygon using the coordinate (Shoelace /
    Gauss) formula.

    Parameters
    ----------
    points : list of dicts with "northing" and "easting" keys.
             Polygon need not be explicitly closed (last point ≠ first point).
             Minimum 3 points required.

    Returns
    -------
    {"ok": True, "area_m2": float, "n_points": int}

    Notes
    -----
    Area = ½ |Σ (N_i × E_{i+1} − N_{i+1} × E_i)|

    The sign of the raw sum indicates vertex ordering
    (positive = counter-clockwise).
    """
    if len(points) < 3:
        return _err("At least 3 points are required to compute area.")

    coords = []
    for i, pt in enumerate(points):
        n = pt.get("northing")
        e = pt.get("easting")
        if n is None:
            return _err(f"points[{i}] missing 'northing'")
        if e is None:
            return _err(f"points[{i}] missing 'easting'")
        err = _guard_finite(f"points[{i}].northing", n)
        if err:
            return _err(err)
        err = _guard_finite(f"points[{i}].easting", e)
        if err:
            return _err(err)
        coords.append((float(n), float(e)))

    n_pts = len(coords)
    sigma = 0.0
    for i in range(n_pts):
        j = (i + 1) % n_pts
        sigma += coords[i][0] * coords[j][1] - coords[j][0] * coords[i][1]

    area = abs(sigma) / 2.0

    return {
        "ok": True,
        "area_m2": area,
        "n_points": n_pts,
    }


# ---------------------------------------------------------------------------
# 7. Area by DMD (Double Meridian Distance) method
# ---------------------------------------------------------------------------

def area_by_dmd(points: list[dict]) -> dict:
    """
    Compute the area enclosed by a traverse polygon using the
    Double Meridian Distance (DMD) method.

    Parameters
    ----------
    points : list of dicts with "northing" and "easting" keys.
             Same polygon convention as area_by_coordinates.
             Minimum 3 points required.

    Returns
    -------
    {"ok": True, "area_m2": float, "n_points": int,
     "dmd_legs": list of per-leg DMD and 2×area contribution}

    Notes
    -----
    DMD for leg i = DMD_{i-1} + departure_{i-1} + departure_i
    First leg DMD = departure of first leg (standard convention).
    Double Area = Σ (DMD_i × latitude_i)
    Area = |Double Area| / 2
    """
    if len(points) < 3:
        return _err("At least 3 points are required to compute area.")

    coords = []
    for i, pt in enumerate(points):
        n = pt.get("northing")
        e = pt.get("easting")
        if n is None:
            return _err(f"points[{i}] missing 'northing'")
        if e is None:
            return _err(f"points[{i}] missing 'easting'")
        err = _guard_finite(f"points[{i}].northing", n)
        if err:
            return _err(err)
        err = _guard_finite(f"points[{i}].easting", e)
        if err:
            return _err(err)
        coords.append((float(n), float(e)))

    n_pts = len(coords)

    # Compute per-leg latitudes (dN) and departures (dE)
    latitudes = []
    departures = []
    for i in range(n_pts):
        j = (i + 1) % n_pts
        latitudes.append(coords[j][0] - coords[i][0])
        departures.append(coords[j][1] - coords[i][1])

    # Compute DMD for each leg
    dmds = [0.0] * n_pts
    dmds[0] = departures[0]
    for i in range(1, n_pts):
        dmds[i] = dmds[i - 1] + departures[i - 1] + departures[i]

    double_area = sum(dmds[i] * latitudes[i] for i in range(n_pts))
    area = abs(double_area) / 2.0

    dmd_legs = [
        {"leg": i, "latitude": latitudes[i], "departure": departures[i],
         "dmd": dmds[i], "double_area_contrib": dmds[i] * latitudes[i]}
        for i in range(n_pts)
    ]

    return {
        "ok": True,
        "area_m2": area,
        "n_points": n_pts,
        "dmd_legs": dmd_legs,
    }


# ---------------------------------------------------------------------------
# 8. Line–line intersection
# ---------------------------------------------------------------------------

def line_line_intersection(
    p1: dict,
    p2: dict,
    p3: dict,
    p4: dict,
) -> dict:
    """
    Compute the intersection point of two lines (not line segments).
    Lines defined by pairs of points.

    Parameters
    ----------
    p1, p2 : dicts with "northing" and "easting" — first line
    p3, p4 : dicts with "northing" and "easting" — second line

    Returns
    -------
    {"ok": True, "northing": N, "easting": E}
    or {"ok": False, "reason": "Lines are parallel or coincident"}

    Notes
    -----
    Uses the parameterised line intersection formula:
        P = p1 + t × (p2 - p1)
        t = ((p3−p1) × (p4−p3)) / ((p2−p1) × (p4−p3))
    where × denotes the 2D cross product.
    """
    def _get_ne(pt: dict, label: str):
        n = pt.get("northing")
        e = pt.get("easting")
        if n is None:
            return None, None, f"{label} missing 'northing'"
        if e is None:
            return None, None, f"{label} missing 'easting'"
        return float(n), float(e), None

    n1, e1, err = _get_ne(p1, "p1")
    if err:
        return _err(err)
    n2, e2, err = _get_ne(p2, "p2")
    if err:
        return _err(err)
    n3, e3, err = _get_ne(p3, "p3")
    if err:
        return _err(err)
    n4, e4, err = _get_ne(p4, "p4")
    if err:
        return _err(err)

    # Direction vectors
    dN1 = n2 - n1  # type: ignore[operator]
    dE1 = e2 - e1  # type: ignore[operator]
    dN2 = n4 - n3  # type: ignore[operator]
    dE2 = e4 - e3  # type: ignore[operator]

    # Cross product (2D): dN1*dE2 - dE1*dN2
    denom = dN1 * dE2 - dE1 * dN2

    if abs(denom) < 1e-12:
        return _err("Lines are parallel or coincident; no unique intersection.")

    # Parameter t along line 1
    t = ((n3 - n1) * dE2 - (e3 - e1) * dN2) / denom  # type: ignore[operator]

    N = n1 + t * dN1  # type: ignore[operator]
    E = e1 + t * dE1  # type: ignore[operator]

    return {"ok": True, "northing": N, "easting": E}


# ---------------------------------------------------------------------------
# 9. Line–circle intersection
# ---------------------------------------------------------------------------

def line_circle_intersection(
    p1: dict,
    p2: dict,
    centre: dict,
    radius: float,
) -> dict:
    """
    Compute the intersection points of a line (infinite, through p1 and p2)
    with a circle.

    Parameters
    ----------
    p1, p2  : dicts with "northing" and "easting" — two points on the line
    centre  : dict with "northing" and "easting" — circle centre
    radius  : float — circle radius (m); must be > 0

    Returns
    -------
    {"ok": True,
     "intersections": list of dicts with "northing" and "easting",
     "n_intersections": 0, 1, or 2}
    """
    def _get_ne(pt: dict, label: str):
        nn = pt.get("northing")
        ee = pt.get("easting")
        if nn is None:
            return None, None, f"{label} missing 'northing'"
        if ee is None:
            return None, None, f"{label} missing 'easting'"
        return float(nn), float(ee), None

    n1, e1, err = _get_ne(p1, "p1")
    if err:
        return _err(err)
    n2, e2, err = _get_ne(p2, "p2")
    if err:
        return _err(err)
    cn, ce, err = _get_ne(centre, "centre")
    if err:
        return _err(err)
    err2 = _guard_positive("radius", radius)
    if err2:
        return _err(err2)

    r = float(radius)

    # Translate so centre is at origin
    x1, y1 = e1 - ce, n1 - cn  # type: ignore[operator]
    x2, y2 = e2 - ce, n2 - cn  # type: ignore[operator]

    dx, dy = x2 - x1, y2 - y1
    dr2 = dx * dx + dy * dy

    if dr2 < 1e-24:
        return _err("p1 and p2 are coincident; line is undefined.")

    D = x1 * y2 - x2 * y1
    discriminant = r * r * dr2 - D * D

    if discriminant < 0.0:
        return {"ok": True, "intersections": [], "n_intersections": 0}

    sqrt_disc = math.sqrt(max(discriminant, 0.0))
    sgn_dy = -1.0 if dy < 0.0 else 1.0
    dr = math.sqrt(dr2)

    pts = []
    for sign in (1.0, -1.0):
        xi = (D * dy + sign * sgn_dy * dx * sqrt_disc) / dr2
        yi = (-D * dx + sign * abs(dy) * sqrt_disc) / dr2
        pts.append({
            "northing": yi + cn,  # type: ignore[operator]
            "easting": xi + ce,   # type: ignore[operator]
        })

    if discriminant == 0.0:
        pts = [pts[0]]  # tangent: one unique point

    return {
        "ok": True,
        "intersections": pts,
        "n_intersections": len(pts),
    }


# ---------------------------------------------------------------------------
# 10. Point of intersection from two azimuth rays
# ---------------------------------------------------------------------------

def point_of_intersection(
    azimuth1_dd: float,
    n1: float,
    e1: float,
    azimuth2_dd: float,
    n2: float,
    e2: float,
) -> dict:
    """
    Compute the point where two azimuth rays (each from a known station)
    intersect.

    Parameters
    ----------
    azimuth1_dd : float — azimuth from station 1 (decimal degrees)
    n1, e1      : float — coordinates of station 1 (m)
    azimuth2_dd : float — azimuth from station 2 (decimal degrees)
    n2, e2      : float — coordinates of station 2 (m)

    Returns
    -------
    {"ok": True, "northing": N, "easting": E,
     "distance_from_1": float, "distance_from_2": float}
    """
    for name, val in (("azimuth1_dd", azimuth1_dd), ("n1", n1), ("e1", e1),
                      ("azimuth2_dd", azimuth2_dd), ("n2", n2), ("e2", e2)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    az1 = _normalise_azimuth(float(azimuth1_dd))
    az2 = _normalise_azimuth(float(azimuth2_dd))

    # Direction cosines (unit vectors along each ray)
    az1_rad = _deg_to_rad(az1)
    az2_rad = _deg_to_rad(az2)

    dN1, dE1 = math.cos(az1_rad), math.sin(az1_rad)
    dN2, dE2 = math.cos(az2_rad), math.sin(az2_rad)

    # Solve: (n1 + t*dN1, e1 + t*dE1) = (n2 + s*dN2, e2 + s*dE2)
    denom = dN1 * dE2 - dE1 * dN2
    if abs(denom) < 1e-12:
        return _err("Rays are parallel; no unique intersection.")

    dn = float(n2) - float(n1)
    de = float(e2) - float(e1)

    t = (dn * dE2 - de * dN2) / denom
    s = (dn * dE1 - de * dN1) / denom

    N = float(n1) + t * dN1
    E = float(e1) + t * dE1

    return {
        "ok": True,
        "northing": N,
        "easting": E,
        "distance_from_1": abs(t),
        "distance_from_2": abs(s),
    }


# ---------------------------------------------------------------------------
# 11. Resection (three-point resection — Tienstra method)
# ---------------------------------------------------------------------------

def resection(
    p_known: list[dict],
    obs_angles: list[float],
) -> dict:
    """
    Compute the position of an unknown instrument station from observations to
    three known control points (Tienstra method).

    Parameters
    ----------
    p_known : list of exactly 3 dicts, each with "northing" and "easting"
              — the three control points A, B, C in clockwise order as seen
                from the instrument.
    obs_angles : list of exactly 2 floats
              — horizontal angles [alpha, beta] (decimal degrees):
                alpha = angle A→instrument→B
                beta  = angle B→instrument→C

    Returns
    -------
    {"ok": True, "northing": N, "easting": E}

    Notes
    -----
    Tienstra's formula (also called the Tienstra-Collins method):
        K_A = 1 / (cot(A) − cot(alpha))
        K_B = 1 / (cot(B) − cot(beta))
        K_C = 1 / (cot(C) − cot(alpha + beta))
        (N, E) = (K_A*N_A + K_B*N_B + K_C*N_C) / (K_A + K_B + K_C)

    where A, B, C are the interior angles of the triangle formed by the
    three known points at vertices A, B, C respectively.
    """
    if len(p_known) != 3:
        return _err("p_known must contain exactly 3 control points.")
    if len(obs_angles) != 2:
        return _err("obs_angles must contain exactly 2 angles [alpha, beta].")

    coords = []
    for i, pt in enumerate(p_known):
        nn = pt.get("northing")
        ee = pt.get("easting")
        if nn is None:
            return _err(f"p_known[{i}] missing 'northing'")
        if ee is None:
            return _err(f"p_known[{i}] missing 'easting'")
        coords.append((float(nn), float(ee)))

    for i, ang in enumerate(obs_angles):
        err = _guard_finite(f"obs_angles[{i}]", ang)
        if err:
            return _err(err)

    alpha_deg = float(obs_angles[0])
    beta_deg = float(obs_angles[1])

    if alpha_deg <= 0.0 or beta_deg <= 0.0:
        return _err("obs_angles must be positive (in decimal degrees).")

    nA, eA = coords[0]
    nB, eB = coords[1]
    nC, eC = coords[2]

    # Compute triangle interior angles at A, B, C using the law of cosines
    a2 = (nB - nC) ** 2 + (eB - eC) ** 2  # side a (opposite A) = BC
    b2 = (nA - nC) ** 2 + (eA - eC) ** 2  # side b (opposite B) = AC
    c2 = (nA - nB) ** 2 + (eA - eB) ** 2  # side c (opposite C) = AB

    a = math.sqrt(a2)
    b = math.sqrt(b2)
    c = math.sqrt(c2)

    if a < 1e-12 or b < 1e-12 or c < 1e-12:
        return _err("Control points are collinear or coincident.")

    # Interior angles of triangle
    cos_A = (b2 + c2 - a2) / (2.0 * b * c)
    cos_B = (a2 + c2 - b2) / (2.0 * a * c)
    cos_C = (a2 + b2 - c2) / (2.0 * a * b)

    cos_A = max(-1.0, min(1.0, cos_A))
    cos_B = max(-1.0, min(1.0, cos_B))
    cos_C = max(-1.0, min(1.0, cos_C))

    ang_A = math.acos(cos_A)
    ang_B = math.acos(cos_B)
    ang_C = math.acos(cos_C)

    alpha_rad = _deg_to_rad(alpha_deg)
    beta_rad = _deg_to_rad(beta_deg)
    gamma_rad = alpha_rad + beta_rad  # angle C→instrument→A

    def _cot(x: float) -> float:
        s = math.sin(x)
        if abs(s) < 1e-14:
            return math.copysign(float("inf"), math.cos(x))
        return math.cos(x) / s

    denom_A = _cot(ang_A) - _cot(alpha_rad)
    denom_B = _cot(ang_B) - _cot(beta_rad)
    denom_C = _cot(ang_C) - _cot(gamma_rad)

    if abs(denom_A) < 1e-14 or abs(denom_B) < 1e-14 or abs(denom_C) < 1e-14:
        return _err(
            "Degenerate resection geometry: instrument station on circumcircle "
            "of the three control points (the 'danger circle')."
        )

    KA = 1.0 / denom_A
    KB = 1.0 / denom_B
    KC = 1.0 / denom_C

    denom_sum = KA + KB + KC
    if abs(denom_sum) < 1e-14:
        return _err("Degenerate resection: KA + KB + KC ≈ 0.")

    N = (KA * nA + KB * nB + KC * nC) / denom_sum
    E = (KA * eA + KB * eB + KC * eC) / denom_sum

    return {
        "ok": True,
        "northing": N,
        "easting": E,
        "KA": KA,
        "KB": KB,
        "KC": KC,
    }


# ---------------------------------------------------------------------------
# 12. Level-loop adjustment
# ---------------------------------------------------------------------------

def level_loop_adjust(
    observations: list[dict],
    known_elev: float,
) -> dict:
    """
    Adjust a closed level loop by distributing misclosure proportionally
    to the distance of each observed height difference.

    Parameters
    ----------
    observations : list of dicts, each with:
        "distance" : float — sight distance (m) for this leg; must be >= 0
        "delta_h"  : float — observed height difference (m) for this leg
                             (positive = rise, negative = fall)
    known_elev : float — starting benchmark elevation (m)

    Returns
    -------
    {"ok": True,
     "misclosure": float — total loop misclosure (m),
     "adjusted_observations": list of dicts with corrected "delta_h",
     "adjusted_elevations": list of float — cumulative elevation at each
                            station (including start and end station),
     "total_distance": float,
     "precision_ratio": misclosure / total_distance (0 if dist=0)}

    Notes
    -----
    Correction per leg = -misclosure × (distance_i / total_distance)
    If all distances are zero, corrections are distributed equally.
    """
    if not observations:
        return _err("observations must not be empty")

    err = _guard_finite("known_elev", known_elev)
    if err:
        return _err(err)

    raw_dh = []
    raw_dist = []

    for i, obs in enumerate(observations):
        dh = obs.get("delta_h")
        dist = obs.get("distance")
        if dh is None:
            return _err(f"observations[{i}] missing 'delta_h'")
        if dist is None:
            return _err(f"observations[{i}] missing 'distance'")
        err2 = _guard_finite(f"observations[{i}].delta_h", dh)
        if err2:
            return _err(err2)
        err3 = _guard_nonneg(f"observations[{i}].distance", dist)
        if err3:
            return _err(err3)
        raw_dh.append(float(dh))
        raw_dist.append(float(dist))

    misclosure = sum(raw_dh)
    total_dist = sum(raw_dist)

    n_legs = len(raw_dh)

    if total_dist > 0.0:
        corrections = [-misclosure * (d / total_dist) for d in raw_dist]
        precision_ratio = abs(misclosure) / total_dist if total_dist > 0 else 0.0
    else:
        # Distribute equally if no distance info
        corr = -misclosure / n_legs
        corrections = [corr] * n_legs
        precision_ratio = 0.0

    adjusted_dh = [raw_dh[i] + corrections[i] for i in range(n_legs)]

    # Compute adjusted elevations
    elevations = [float(known_elev)]
    elev = float(known_elev)
    for dh in adjusted_dh:
        elev += dh
        elevations.append(elev)

    adjusted_obs = [
        {
            "distance": raw_dist[i],
            "delta_h": adjusted_dh[i],
            "correction": corrections[i],
            "original_delta_h": raw_dh[i],
        }
        for i in range(n_legs)
    ]

    return {
        "ok": True,
        "misclosure": misclosure,
        "adjusted_observations": adjusted_obs,
        "adjusted_elevations": elevations,
        "total_distance": total_dist,
        "precision_ratio": precision_ratio,
    }
