"""
kerf_cad_core.geodesy.geo — Geodetic computation & map projection.

Pure-Python (math only). No external dependencies.

Coordinate systems
------------------
  Geodetic  : (lat_deg, lon_deg, h_m)  — WGS84/GRS80/Clarke1866 ellipsoid
  ECEF      : (X, Y, Z) metres — Earth-Centred Earth-Fixed
  ENU       : (e, n, u) metres — local East-North-Up tangent plane
  UTM       : (easting, northing, zone, hemisphere)
  LCC       : (easting, northing) — Lambert Conformal Conic
  Web Mercator : (x, y) — EPSG:3857

Map projections
---------------
  transverse_mercator_fwd / _inv  — Krüger series (same precision as Karney 2011 series-6)
  utm_fwd / utm_inv               — UTM wrapper (zone + false origin)
  lcc_fwd / lcc_inv               — Lambert Conformal Conic (1- & 2-parallel)
  web_mercator_fwd / _inv         — Spherical Web Mercator

Geodesy
-------
  vincenty_inverse  — geodesic distance & azimuth, antipodal fallback to Haversine
  vincenty_direct   — geodesic destination from start + azimuth + distance
  haversine         — great-circle distance on a sphere
  rhumb_line        — rhumb distance & bearing
  meridian_arc      — M(lat) arc length from equator
  radius_curvature  — (M, N) radii of curvature in meridian and prime vertical
  geodetic_to_ecef  — Bowring/closed-form
  ecef_to_geodetic  — Bowring iterative inverse
  ecef_to_enu       — ECEF → local tangent ENU
  enu_to_ecef       — ENU → ECEF
  grid_to_ground    — combined scale factor (projection + elevation)

Notes
-----
  Geoid undulation: all heights are ellipsoidal unless otherwise noted.
  To convert to/from orthometric height H: h_ellipsoidal = H + N_geoid.
  Geoid undulations are NOT computed here; use EGM2008 / GEOID18 externally.

References
----------
Bowring (1976) "Transformation from spatial to geographical coordinates"
Karney (2011) "Transverse Mercator with an accuracy of a few nanometres"
Krüger (1912) "Konforme Abbildung des Erdellipsoids in der Ebene"
Vincenty (1975) "Direct and inverse solutions of geodesics on the ellipsoid"
NIMA TR8350.2 (1997) "Department of Defense WGS-84"
EPSG Guidance Note 7-2 (2023) — Map projections

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import NamedTuple, Tuple

# ---------------------------------------------------------------------------
# Ellipsoid definitions
# ---------------------------------------------------------------------------

class Ellipsoid(NamedTuple):
    name: str
    a: float   # semi-major axis (m)
    f: float   # flattening (1/f reciprocal given for readability)


def _ellipsoid(name: str, a: float, inv_f: float) -> Ellipsoid:
    return Ellipsoid(name=name, a=a, f=1.0 / inv_f)


WGS84      = _ellipsoid("WGS84",       6_378_137.0,     298.257223563)
GRS80      = _ellipsoid("GRS80",       6_378_137.0,     298.257222101)
CLARKE1866 = _ellipsoid("Clarke1866",  6_378_206.4,     294.978698214)

_ELLIPSOIDS: dict[str, Ellipsoid] = {
    "WGS84":      WGS84,
    "GRS80":      GRS80,
    "Clarke1866": CLARKE1866,
}

_DEFAULT_ELLIPSOID = WGS84


def _get_ellipsoid(name: str | None) -> Ellipsoid:
    if name is None:
        return _DEFAULT_ELLIPSOID
    e = _ELLIPSOIDS.get(name)
    if e is None:
        raise ValueError(f"Unknown ellipsoid '{name}'. Choose from {list(_ELLIPSOIDS)}")
    return e


def _derived(ell: Ellipsoid) -> Tuple[float, float, float, float]:
    """Return (b, e2, ep2, n) from ellipsoid."""
    a, f = ell.a, ell.f
    b   = a * (1.0 - f)
    e2  = 2.0 * f - f * f            # first eccentricity squared
    ep2 = e2 / (1.0 - e2)            # second eccentricity squared
    n   = f / (2.0 - f)              # third flattening
    return b, e2, ep2, n


# ---------------------------------------------------------------------------
# Radii of curvature
# ---------------------------------------------------------------------------

def radius_curvature(lat_deg: float, ellipsoid: str | None = None) -> dict:
    """
    Radii of curvature M (meridian) and N (prime vertical) at geodetic latitude.

    Parameters
    ----------
    lat_deg  : geodetic latitude (degrees)
    ellipsoid: 'WGS84' | 'GRS80' | 'Clarke1866' (default WGS84)

    Returns
    -------
    {'M_m': float, 'N_m': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    _, e2, _, _ = _derived(ell)
    a = ell.a
    phi = math.radians(lat_deg)
    W = math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
    N = a / W
    M = a * (1.0 - e2) / (W ** 3)
    return {"M_m": M, "N_m": N}


# ---------------------------------------------------------------------------
# Meridian arc
# ---------------------------------------------------------------------------

def meridian_arc(lat_deg: float, ellipsoid: str | None = None) -> float:
    """
    Meridian arc length (metres) from the equator to geodetic latitude.

    Uses the Helmert series in powers of e^2, accurate to sub-millimetre.
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    e2 = ell.f * (2.0 - ell.f)
    e4 = e2 * e2
    e6 = e4 * e2
    e8 = e6 * e2
    # Helmert/Helmert-Bessel coefficients
    A0 = 1.0      - e2 / 4.0  - 3.0 * e4 / 64.0  - 5.0 * e6 / 256.0   - 175.0 * e8 / 16384.0
    A2 = 3.0 / 8.0 * (e2 + e4 / 4.0 + 15.0 * e6 / 128.0 + 35.0 * e8 / 512.0)
    A4 = 15.0 / 256.0 * (e4 + 3.0 * e6 / 4.0 + 35.0 * e8 / 64.0)
    A6 = 35.0 / 3072.0 * (e6 + 5.0 * e8 / 4.0)
    A8 = 315.0 / 131072.0 * e8
    phi = math.radians(lat_deg)
    return a * (
        A0 * phi
        - A2 * math.sin(2.0 * phi)
        + A4 * math.sin(4.0 * phi)
        - A6 * math.sin(6.0 * phi)
        + A8 * math.sin(8.0 * phi)
    )


# ---------------------------------------------------------------------------
# Geodetic ↔ ECEF (Bowring)
# ---------------------------------------------------------------------------

def geodetic_to_ecef(
    lat_deg: float,
    lon_deg: float,
    h_m: float = 0.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Convert geodetic (lat, lon, h) to ECEF (X, Y, Z) metres.

    Parameters
    ----------
    lat_deg  : geodetic latitude (degrees, –90..90)
    lon_deg  : geodetic longitude (degrees, –180..180)
    h_m      : ellipsoidal height (metres, default 0)
    ellipsoid: datum name (default WGS84)

    Returns
    -------
    {'X_m': float, 'Y_m': float, 'Z_m': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    _, e2, _, _ = _derived(ell)
    a = ell.a
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg)
    N = a / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
    X = (N + h_m) * math.cos(phi) * math.cos(lam)
    Y = (N + h_m) * math.cos(phi) * math.sin(lam)
    Z = (N * (1.0 - e2) + h_m) * math.sin(phi)
    return {"X_m": X, "Y_m": Y, "Z_m": Z}


def ecef_to_geodetic(
    X: float,
    Y: float,
    Z: float,
    ellipsoid: str | None = None,
    max_iter: int = 10,
) -> dict:
    """
    Convert ECEF (X, Y, Z) to geodetic (lat, lon, h) — Bowring iterative.

    Parameters
    ----------
    X, Y, Z  : ECEF coordinates (metres)
    ellipsoid: datum name (default WGS84)
    max_iter : Bowring iteration limit (default 10, converges in 2–3)

    Returns
    -------
    {'lat_deg': float, 'lon_deg': float, 'h_m': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    _, e2, ep2, _ = _derived(ell)
    b = a * (1.0 - ell.f)

    p = math.hypot(X, Y)
    lon = math.atan2(Y, X)

    # Bowring's initial approximation
    theta = math.atan2(Z * a, p * b)
    phi = math.atan2(
        Z + ep2 * b * math.sin(theta) ** 3,
        p - e2 * a * math.cos(theta) ** 3,
    )
    for _ in range(max_iter):
        phi_prev = phi
        N = a / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(Z + e2 * N * math.sin(phi), p)
        if abs(phi - phi_prev) < 1e-12:
            break

    N = a / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
    if abs(phi) > math.radians(45.0):
        h = Z / math.sin(phi) - N * (1.0 - e2)
    else:
        h = p / math.cos(phi) - N

    return {
        "lat_deg": math.degrees(phi),
        "lon_deg": math.degrees(lon),
        "h_m": h,
    }


# ---------------------------------------------------------------------------
# ECEF ↔ ENU
# ---------------------------------------------------------------------------

def ecef_to_enu(
    X: float, Y: float, Z: float,
    ref_lat_deg: float, ref_lon_deg: float, ref_h_m: float = 0.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Convert ECEF point to ENU relative to a reference geodetic origin.

    Returns
    -------
    {'e_m': float, 'n_m': float, 'u_m': float}
    """
    ref = geodetic_to_ecef(ref_lat_deg, ref_lon_deg, ref_h_m, ellipsoid)
    dX = X - ref["X_m"]
    dY = Y - ref["Y_m"]
    dZ = Z - ref["Z_m"]
    phi = math.radians(ref_lat_deg)
    lam = math.radians(ref_lon_deg)
    sp, cp = math.sin(phi), math.cos(phi)
    sl, cl = math.sin(lam), math.cos(lam)
    e =  -sl * dX + cl * dY
    n =  -sp * cl * dX - sp * sl * dY + cp * dZ
    u =   cp * cl * dX + cp * sl * dY + sp * dZ
    return {"e_m": e, "n_m": n, "u_m": u}


def enu_to_ecef(
    e: float, n: float, u: float,
    ref_lat_deg: float, ref_lon_deg: float, ref_h_m: float = 0.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Convert ENU (relative to reference origin) back to ECEF.

    Returns
    -------
    {'X_m': float, 'Y_m': float, 'Z_m': float}
    """
    ref = geodetic_to_ecef(ref_lat_deg, ref_lon_deg, ref_h_m, ellipsoid)
    phi = math.radians(ref_lat_deg)
    lam = math.radians(ref_lon_deg)
    sp, cp = math.sin(phi), math.cos(phi)
    sl, cl = math.sin(lam), math.cos(lam)
    X = ref["X_m"] + (-sl * e - sp * cl * n + cp * cl * u)
    Y = ref["Y_m"] + ( cl * e - sp * sl * n + cp * sl * u)
    Z = ref["Z_m"] + (          cp      * n + sp      * u)
    return {"X_m": X, "Y_m": Y, "Z_m": Z}


# ---------------------------------------------------------------------------
# Transverse Mercator (Krüger series)
# ---------------------------------------------------------------------------
# Implements the Krüger (1912) / Karney (2011) 6-term series giving
# sub-millimetre accuracy across the full TM strip.

def _tm_series_coeffs(n: float) -> Tuple[list, list]:
    """
    Krüger α (forward) and β (inverse) series coefficients up to order 6.
    Returns (alpha[1..6], beta[1..6]) — index 0 unused.
    """
    n2 = n * n
    n3 = n2 * n
    n4 = n3 * n
    n5 = n4 * n
    n6 = n5 * n

    alpha = [0.0] * 7
    alpha[1] = (1.0/2)*n - (2.0/3)*n2 + (5.0/16)*n3 + (41.0/180)*n4 - (127.0/288)*n5 + (7891.0/37800)*n6
    alpha[2] = (13.0/48)*n2 - (3.0/5)*n3 + (557.0/1440)*n4 + (281.0/630)*n5 - (1983433.0/1935360)*n6
    alpha[3] = (61.0/240)*n3 - (103.0/140)*n4 + (15061.0/26880)*n5 + (167603.0/181440)*n6
    alpha[4] = (49561.0/161280)*n4 - (179.0/168)*n5 + (6601661.0/7257600)*n6
    alpha[5] = (34729.0/80640)*n5 - (3418313.0/1995840)*n6
    alpha[6] = (212378941.0/319334400)*n6

    beta = [0.0] * 7
    beta[1] = -(1.0/2)*n + (2.0/3)*n2 - (37.0/96)*n3 + (1.0/360)*n4 + (81.0/512)*n5 - (96199.0/604800)*n6
    beta[2] = -(1.0/48)*n2 - (1.0/15)*n3 + (437.0/1440)*n4 - (46.0/105)*n5 + (1118711.0/3870720)*n6
    beta[3] = -(17.0/480)*n3 + (37.0/840)*n4 + (209.0/4480)*n5 - (5569.0/90720)*n6
    beta[4] = -(4397.0/161280)*n4 + (11.0/504)*n5 + (830251.0/7257600)*n6
    beta[5] = -(4583.0/161280)*n5 + (108847.0/3991680)*n6
    beta[6] = -(20648693.0/638668800)*n6

    return alpha, beta


def transverse_mercator_fwd(
    lat_deg: float,
    lon_deg: float,
    lon0_deg: float,
    k0: float = 1.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Transverse Mercator forward projection (Krüger/Karney 6-term series).

    Parameters
    ----------
    lat_deg  : geodetic latitude (degrees)
    lon_deg  : geodetic longitude (degrees)
    lon0_deg : central meridian (degrees)
    k0       : central-meridian scale factor (default 1.0)
    ellipsoid: datum (default WGS84)

    Returns
    -------
    {'xi_m': float, 'eta_m': float, 'k': float, 'gamma_deg': float}
    xi  = northing from equator (before false origin), eta = easting from CM
    k   = point scale factor, gamma = meridian convergence (degrees)
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    _, _, _, n = _derived(ell)
    alpha, _ = _tm_series_coeffs(n)

    A = a / (1.0 + n) * (1.0 + n**2 / 4.0 + n**4 / 64.0)

    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg - lon0_deg)

    e2 = ell.f * (2.0 - ell.f)
    e  = math.sqrt(e2)

    tau = math.tan(phi)
    # Conformal-latitude tangent tau' (Karney 2011 eq 7–9)
    sigma = math.sinh(e * math.atanh(e * math.sin(phi)))
    tau_prime = tau * math.sqrt(1.0 + sigma**2) - sigma * math.sqrt(1.0 + tau**2)

    xi0 = math.atan2(tau_prime, math.cos(lam))
    eta0 = math.asinh(math.sin(lam) / math.sqrt(tau_prime**2 + math.cos(lam)**2))

    xi = xi0
    eta = eta0
    for j in range(1, 7):
        xi  += alpha[j] * math.sin(2.0 * j * xi0) * math.cosh(2.0 * j * eta0)
        eta += alpha[j] * math.cos(2.0 * j * xi0) * math.sinh(2.0 * j * eta0)

    # point scale factor
    p_prime = 1.0
    q_prime = 0.0
    for j in range(1, 7):
        p_prime += 2.0 * j * alpha[j] * math.cos(2.0 * j * xi0) * math.cosh(2.0 * j * eta0)
        q_prime += 2.0 * j * alpha[j] * math.sin(2.0 * j * xi0) * math.sinh(2.0 * j * eta0)

    # Point scale factor (Karney 2011 eq. 25):
    #   k = k0 * (A/a) * sqrt(p'^2 + q'^2)
    #         * sqrt((1 + tan^2 phi) * (1 - e2 sin^2 phi)) / sqrt(tau'^2 + cos^2 lam)
    # The sec(phi)=sqrt(1+tan^2 phi) and W=sqrt(1-e2 sin^2 phi) factors are in
    # the NUMERATOR (k must equal k0 on the central meridian).
    dn = math.sqrt(tau_prime**2 + math.cos(lam)**2)
    sec2_W = math.sqrt((1.0 + tau**2) * (1.0 - e2 * math.sin(phi)**2))
    k_scale = k0 * (A / a) * math.hypot(p_prime, q_prime) * sec2_W / dn

    # convergence
    gamma = math.atan2(
        q_prime * math.sqrt(tau_prime**2 + math.cos(lam)**2) + p_prime * tau_prime * math.tan(lam),
        p_prime * math.sqrt(tau_prime**2 + math.cos(lam)**2) - q_prime * tau_prime * math.tan(lam),
    )

    return {
        "xi_m":    A * k0 * xi,
        "eta_m":   A * k0 * eta,
        "k":       k_scale,
        "gamma_deg": math.degrees(gamma),
    }


def transverse_mercator_inv(
    xi_m: float,
    eta_m: float,
    lon0_deg: float,
    k0: float = 1.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Transverse Mercator inverse projection (Krüger/Karney 6-term series).

    Parameters
    ----------
    xi_m     : northing from equator (raw, before false origin) in metres
    eta_m    : easting from central meridian (raw) in metres
    lon0_deg : central meridian (degrees)
    k0       : central-meridian scale factor
    ellipsoid: datum

    Returns
    -------
    {'lat_deg': float, 'lon_deg': float, 'k': float, 'gamma_deg': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    e2 = ell.f * (2.0 - ell.f)
    e = math.sqrt(e2)
    _, _, _, n = _derived(ell)
    _, beta = _tm_series_coeffs(n)

    A = a / (1.0 + n) * (1.0 + n**2 / 4.0 + n**4 / 64.0)

    # Normalised TM coordinates
    xi  = xi_m  / (A * k0)
    eta = eta_m / (A * k0)

    # Inverse Krüger series: (xi, eta) → (xi', eta') = conformal-lat sphere plane.
    # beta[j] are negative; adding them subtracts the forward-series corrections.
    xi_p  = xi
    eta_p = eta
    for j in range(1, 7):
        xi_p  += beta[j] * math.sin(2.0 * j * xi) * math.cosh(2.0 * j * eta)
        eta_p += beta[j] * math.cos(2.0 * j * xi) * math.sinh(2.0 * j * eta)

    # Conformal-latitude tangent from rectifying-latitude quantities
    # tau' = sinh(eta') / cos(xi')  ... but use atan2 form for robustness
    tau_prime = math.sin(xi_p) / math.sqrt(math.sinh(eta_p)**2 + math.cos(xi_p)**2)
    lam = math.atan2(math.sinh(eta_p), math.cos(xi_p))

    # Recover geodetic latitude from conformal-latitude tangent (Newton iteration).
    # tau' = tan(chi); chi is the conformal latitude; iterate to get geodetic phi.
    # Use linearised step: d(tau')/d(tau) ≈ (1 - e2) so dphi = residual / ((1-e2)*(1+t^2))
    phi = math.atan(tau_prime)
    for _ in range(20):
        phi_prev = phi
        s = math.sinh(e * math.atanh(e * math.sin(phi)))
        t = math.tan(phi)
        t_prime_est = t * math.sqrt(1.0 + s**2) - s * math.sqrt(1.0 + t**2)
        dphi = (tau_prime - t_prime_est) / ((1.0 - e2) * (1.0 + t**2))
        phi += dphi
        if abs(phi - phi_prev) < 1e-13:
            break

    # Point scale factor and meridian convergence are recovered by re-running
    # the FORWARD α-series at the solved geodetic position. This guarantees
    # exact round-trip consistency with transverse_mercator_fwd (whose k/γ
    # are validated against Snyder USGS PP1395) and avoids the subtle β-series
    # convergence error of an independent inverse derivation. The horizontal
    # position (phi, lam) above is unchanged.
    cos_phi = math.cos(phi)
    if cos_phi > 1e-14:
        fwd = transverse_mercator_fwd(
            math.degrees(phi),
            math.degrees(lam) + lon0_deg,
            lon0_deg,
            k0=k0,
            ellipsoid=ellipsoid,
        )
        k_scale = fwd["k"]
        gamma_deg = fwd["gamma_deg"]
    else:
        k_scale = k0
        gamma_deg = 0.0

    return {
        "lat_deg":   math.degrees(phi),
        "lon_deg":   math.degrees(lam) + lon0_deg,
        "k":         k_scale,
        "gamma_deg": gamma_deg,
    }


# ---------------------------------------------------------------------------
# UTM
# ---------------------------------------------------------------------------

_UTM_K0 = 0.9996
_UTM_E0 = 500_000.0   # false easting (m)
_UTM_N0_S = 10_000_000.0  # false northing for southern hemisphere


def utm_zone_from_lon(lon_deg: float) -> int:
    """Return UTM zone number (1–60) from longitude."""
    return int((lon_deg + 180.0) / 6.0) % 60 + 1


def utm_lon0(zone: int) -> float:
    """Central meridian (degrees) for UTM zone."""
    return (zone - 1) * 6.0 - 180.0 + 3.0


def utm_fwd(
    lat_deg: float,
    lon_deg: float,
    zone: int | None = None,
    ellipsoid: str | None = None,
) -> dict:
    """
    Forward UTM projection.

    Parameters
    ----------
    lat_deg  : geodetic latitude (degrees, –80..84)
    lon_deg  : geodetic longitude (degrees)
    zone     : UTM zone (1–60). Derived from lon_deg if omitted.
    ellipsoid: datum (default WGS84)

    Returns
    -------
    {'easting_m': float, 'northing_m': float, 'zone': int, 'hemisphere': str,
     'k': float, 'gamma_deg': float}
    """
    if zone is None:
        zone = utm_zone_from_lon(lon_deg)
    lon0 = utm_lon0(zone)
    hemisphere = "N" if lat_deg >= 0.0 else "S"

    tm = transverse_mercator_fwd(lat_deg, lon_deg, lon0, k0=_UTM_K0, ellipsoid=ellipsoid)
    easting  = tm["eta_m"] + _UTM_E0
    northing = tm["xi_m"]
    if hemisphere == "S":
        northing += _UTM_N0_S

    return {
        "easting_m":  easting,
        "northing_m": northing,
        "zone":       zone,
        "hemisphere": hemisphere,
        "k":          tm["k"],
        "gamma_deg":  tm["gamma_deg"],
    }


def utm_inv(
    easting_m: float,
    northing_m: float,
    zone: int,
    hemisphere: str = "N",
    ellipsoid: str | None = None,
) -> dict:
    """
    Inverse UTM projection.

    Returns
    -------
    {'lat_deg': float, 'lon_deg': float, 'k': float, 'gamma_deg': float}
    """
    lon0 = utm_lon0(zone)
    eta_m = easting_m - _UTM_E0
    xi_m  = northing_m
    if hemisphere.upper() == "S":
        xi_m -= _UTM_N0_S

    r = transverse_mercator_inv(xi_m, eta_m, lon0, k0=_UTM_K0, ellipsoid=ellipsoid)
    return {
        "lat_deg":   r["lat_deg"],
        "lon_deg":   r["lon_deg"],
        "k":         r["k"],
        "gamma_deg": r["gamma_deg"],
    }


# ---------------------------------------------------------------------------
# Lambert Conformal Conic (LCC)
# ---------------------------------------------------------------------------

def lcc_fwd(
    lat_deg: float,
    lon_deg: float,
    lat0_deg: float,
    lon0_deg: float,
    lat1_deg: float,
    lat2_deg: float | None = None,
    FE: float = 0.0,
    FN: float = 0.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Lambert Conformal Conic forward projection (1- or 2-parallel).

    Parameters
    ----------
    lat_deg / lon_deg : point to project (degrees)
    lat0_deg          : latitude of false origin
    lon0_deg          : central meridian
    lat1_deg          : first standard parallel
    lat2_deg          : second standard parallel (None → 1-parallel)
    FE / FN           : false easting / northing (metres)
    ellipsoid         : datum (default WGS84)

    Returns
    -------
    {'easting_m': float, 'northing_m': float, 'k': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    e2 = ell.f * (2.0 - ell.f)
    e  = math.sqrt(e2)
    a  = ell.a

    def _t(phi: float) -> float:
        sin_phi = math.sin(phi)
        return math.tan(math.pi / 4.0 - phi / 2.0) / (
            ((1.0 - e * sin_phi) / (1.0 + e * sin_phi)) ** (e / 2.0)
        )

    def _m(phi: float) -> float:
        sin_phi = math.sin(phi)
        return math.cos(phi) / math.sqrt(1.0 - e2 * sin_phi**2)

    phi1 = math.radians(lat1_deg)
    if lat2_deg is None or abs(lat2_deg - lat1_deg) < 1e-10:
        # 1-parallel
        m1 = _m(phi1)
        t1 = _t(phi1)
        if t1 <= 0.0:
            n = math.sin(phi1)
        else:
            n = math.sin(phi1)
        F = m1 / (n * t1**n) if abs(n) > 1e-14 and t1 > 0 else m1
        n = math.sin(phi1)
    else:
        phi2 = math.radians(lat2_deg)
        m1, m2 = _m(phi1), _m(phi2)
        t1, t2 = _t(phi1), _t(phi2)
        if abs(t1 - t2) < 1e-14:
            n = math.sin(phi1)
        else:
            n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
        F = m1 / (n * t1**n)

    phi0 = math.radians(lat0_deg)
    t0 = _t(phi0)
    rho0 = a * F * t0**n

    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg - lon0_deg)

    t   = _t(phi)
    rho = a * F * t**n
    theta = n * lam

    k = rho * n / (a * _m(phi))

    return {
        "easting_m":  FE + rho  * math.sin(theta),
        "northing_m": FN + rho0 - rho * math.cos(theta),
        "k":          k,
    }


def lcc_inv(
    easting_m: float,
    northing_m: float,
    lat0_deg: float,
    lon0_deg: float,
    lat1_deg: float,
    lat2_deg: float | None = None,
    FE: float = 0.0,
    FN: float = 0.0,
    ellipsoid: str | None = None,
) -> dict:
    """
    Lambert Conformal Conic inverse projection.

    Returns
    -------
    {'lat_deg': float, 'lon_deg': float}
    """
    ell = _get_ellipsoid(ellipsoid)
    e2 = ell.f * (2.0 - ell.f)
    e  = math.sqrt(e2)
    a  = ell.a

    def _t(phi: float) -> float:
        sin_phi = math.sin(phi)
        return math.tan(math.pi / 4.0 - phi / 2.0) / (
            ((1.0 - e * sin_phi) / (1.0 + e * sin_phi)) ** (e / 2.0)
        )

    def _m(phi: float) -> float:
        sin_phi = math.sin(phi)
        return math.cos(phi) / math.sqrt(1.0 - e2 * sin_phi**2)

    phi1 = math.radians(lat1_deg)
    if lat2_deg is None or abs(lat2_deg - lat1_deg) < 1e-10:
        n = math.sin(phi1)
        m1 = _m(phi1)
        t1 = _t(phi1)
        F = m1 / (n * t1**n) if abs(n) > 1e-14 and t1 > 0 else m1
    else:
        phi2 = math.radians(lat2_deg)
        m1, m2 = _m(phi1), _m(phi2)
        t1, t2 = _t(phi1), _t(phi2)
        if abs(t1 - t2) < 1e-14:
            n = math.sin(phi1)
        else:
            n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
        F = m1 / (n * t1**n)

    phi0 = math.radians(lat0_deg)
    t0   = _t(phi0)
    rho0 = a * F * t0**n

    x = easting_m - FE
    y = northing_m - FN

    rho_prime = math.copysign(math.hypot(x, rho0 - y), n)
    t_prime   = (rho_prime / (a * F)) ** (1.0 / n)
    theta_prime = math.atan2(x, rho0 - y)

    # phi by iteration
    phi = math.pi / 2.0 - 2.0 * math.atan(t_prime)
    for _ in range(20):
        phi_prev = phi
        sin_phi  = math.sin(phi)
        phi = math.pi / 2.0 - 2.0 * math.atan(
            t_prime * ((1.0 - e * sin_phi) / (1.0 + e * sin_phi)) ** (e / 2.0)
        )
        if abs(phi - phi_prev) < 1e-12:
            break

    lam = theta_prime / n + math.radians(lon0_deg)
    return {"lat_deg": math.degrees(phi), "lon_deg": math.degrees(lam)}


# ---------------------------------------------------------------------------
# Web Mercator (EPSG:3857 / Pseudo Mercator)
# ---------------------------------------------------------------------------

_WM_R = 6_378_137.0   # Sphere radius (same as WGS84 a)


def web_mercator_fwd(lat_deg: float, lon_deg: float) -> dict:
    """
    Web Mercator (EPSG:3857) forward projection (spherical).

    Returns
    -------
    {'x_m': float, 'y_m': float}
    """
    if abs(lat_deg) > 85.051129:
        warnings.warn(
            f"web_mercator_fwd: lat_deg={lat_deg} outside valid range ±85.05°; "
            "result may be extreme.",
            stacklevel=2,
        )
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg)
    x = _WM_R * lam
    y = _WM_R * math.log(math.tan(math.pi / 4.0 + phi / 2.0))
    return {"x_m": x, "y_m": y}


def web_mercator_inv(x_m: float, y_m: float) -> dict:
    """
    Web Mercator (EPSG:3857) inverse projection.

    Returns
    -------
    {'lat_deg': float, 'lon_deg': float}
    """
    lon = math.degrees(x_m / _WM_R)
    lat = math.degrees(2.0 * math.atan(math.exp(y_m / _WM_R)) - math.pi / 2.0)
    return {"lat_deg": lat, "lon_deg": lon}


# ---------------------------------------------------------------------------
# Haversine great-circle distance
# ---------------------------------------------------------------------------

def haversine(
    lat1_deg: float, lon1_deg: float,
    lat2_deg: float, lon2_deg: float,
    radius_m: float = 6_371_008.8,
) -> dict:
    """
    Haversine great-circle distance between two points on a sphere.

    Parameters
    ----------
    lat1_deg, lon1_deg : first point (degrees)
    lat2_deg, lon2_deg : second point (degrees)
    radius_m           : sphere radius (default IUGG mean Earth radius 6 371 008.8 m)

    Returns
    -------
    {'distance_m': float, 'az12_deg': float, 'az21_deg': float}
    """
    phi1 = math.radians(lat1_deg)
    phi2 = math.radians(lat2_deg)
    dphi = math.radians(lat2_deg - lat1_deg)
    dlam = math.radians(lon2_deg - lon1_deg)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    dist = radius_m * c

    az12 = math.atan2(
        math.sin(dlam) * math.cos(phi2),
        math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam),
    )
    az21 = math.atan2(
        math.sin(dlam) * math.cos(phi1),
        math.cos(phi2) * math.sin(phi1) - math.sin(phi2) * math.cos(phi1) * math.cos(dlam),
    ) + math.pi

    return {
        "distance_m": dist,
        "az12_deg":   (math.degrees(az12) + 360.0) % 360.0,
        "az21_deg":   (math.degrees(az21) + 360.0) % 360.0,
    }


# ---------------------------------------------------------------------------
# Rhumb line
# ---------------------------------------------------------------------------

def rhumb_line(
    lat1_deg: float, lon1_deg: float,
    lat2_deg: float, lon2_deg: float,
    ellipsoid: str | None = None,
) -> dict:
    """
    Rhumb-line (loxodrome) distance and bearing between two points.

    Uses the meridian-arc formula for the ellipsoid.

    Returns
    -------
    {'distance_m': float, 'bearing_deg': float}
    """
    ell = _get_ellipsoid(ellipsoid)

    def _isometric(phi: float) -> float:
        """Isometric latitude (Mercator ordinate) on the ellipsoid."""
        e = math.sqrt(ell.f * (2.0 - ell.f))
        sin_phi = math.sin(phi)
        return math.log(math.tan(math.pi / 4.0 + phi / 2.0) * (
            (1.0 - e * sin_phi) / (1.0 + e * sin_phi)
        ) ** (e / 2.0))

    phi1 = math.radians(lat1_deg)
    phi2 = math.radians(lat2_deg)
    dlam = math.radians(lon2_deg - lon1_deg)
    # Ensure dlam in [−π, π]
    dlam = (dlam + math.pi) % (2.0 * math.pi) - math.pi

    dpsi = _isometric(phi2) - _isometric(phi1)
    q = (phi2 - phi1) / dpsi if abs(dpsi) > 1e-11 else math.cos(phi1)

    M1 = meridian_arc(lat1_deg, None)
    M2 = meridian_arc(lat2_deg, None)
    dist = math.hypot((M2 - M1), q * ell.a * dlam)

    bearing = (math.degrees(math.atan2(dlam, dpsi)) + 360.0) % 360.0
    return {"distance_m": dist, "bearing_deg": bearing}


# ---------------------------------------------------------------------------
# Vincenty inverse (geodesic distance & azimuths)
# ---------------------------------------------------------------------------

def vincenty_inverse(
    lat1_deg: float, lon1_deg: float,
    lat2_deg: float, lon2_deg: float,
    ellipsoid: str | None = None,
    tol: float = 1e-12,
    max_iter: int = 1000,
) -> dict:
    """
    Vincenty (1975) inverse solution: geodesic distance & azimuths.

    Antipodal fallback: if Vincenty fails to converge (nearly antipodal
    points), the Haversine great-circle distance on the WGS84 mean sphere
    is returned with a convergence_warning flag.

    Parameters
    ----------
    lat1_deg, lon1_deg : first point (degrees)
    lat2_deg, lon2_deg : second point (degrees)
    ellipsoid          : datum (default WGS84)
    tol                : convergence tolerance (default 1e-12)
    max_iter           : iteration limit (default 1000)

    Returns
    -------
    {'distance_m': float, 'az12_deg': float, 'az21_deg': float,
     'convergence_warning': bool}
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    f = ell.f
    b = a * (1.0 - f)

    phi1 = math.radians(lat1_deg)
    phi2 = math.radians(lat2_deg)
    L    = math.radians(lon2_deg - lon1_deg)

    U1 = math.atan((1.0 - f) * math.tan(phi1))
    U2 = math.atan((1.0 - f) * math.tan(phi2))
    sin_U1, cos_U1 = math.sin(U1), math.cos(U1)
    sin_U2, cos_U2 = math.sin(U2), math.cos(U2)

    lam = L
    converged = False
    sin_sigma = cos_sigma = sigma = sin_alpha = cos2_alpha = cos2_sigma_m = 0.0

    for _ in range(max_iter):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(
            cos_U2 * sin_lam,
            cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lam,
        )
        if sin_sigma == 0.0:
            # coincident points
            return {"distance_m": 0.0, "az12_deg": 0.0, "az21_deg": 0.0,
                    "convergence_warning": False}
        cos_sigma = sin_U1 * sin_U2 + cos_U1 * cos_U2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_U1 * cos_U2 * sin_lam / sin_sigma
        cos2_alpha = 1.0 - sin_alpha**2
        cos2_sigma_m = (cos_sigma - 2.0 * sin_U1 * sin_U2 / cos2_alpha
                        if cos2_alpha != 0.0 else 0.0)
        C = f / 16.0 * cos2_alpha * (4.0 + f * (4.0 - 3.0 * cos2_alpha))
        lam_prev = lam
        lam = L + (1.0 - C) * f * sin_alpha * (
            sigma + C * sin_sigma * (
                cos2_sigma_m + C * cos_sigma * (-1.0 + 2.0 * cos2_sigma_m**2)
            )
        )
        if abs(lam - lam_prev) < tol:
            converged = True
            break

    if not converged:
        warnings.warn(
            "vincenty_inverse: failed to converge (antipodal or near-antipodal "
            "points). Falling back to Haversine.",
            stacklevel=2,
        )
        hav = haversine(lat1_deg, lon1_deg, lat2_deg, lon2_deg)
        return {
            "distance_m":        hav["distance_m"],
            "az12_deg":          hav["az12_deg"],
            "az21_deg":          hav["az21_deg"],
            "convergence_warning": True,
        }

    u2 = cos2_alpha * (a**2 - b**2) / b**2
    A_v = 1.0 + u2 / 16384.0 * (4096.0 + u2 * (-768.0 + u2 * (320.0 - 175.0 * u2)))
    B_v = u2 / 1024.0 * (256.0 + u2 * (-128.0 + u2 * (74.0 - 47.0 * u2)))
    d_sigma = B_v * sin_sigma * (
        cos2_sigma_m + B_v / 4.0 * (
            cos_sigma * (-1.0 + 2.0 * cos2_sigma_m**2)
            - B_v / 6.0 * cos2_sigma_m * (-3.0 + 4.0 * sin_sigma**2) * (-3.0 + 4.0 * cos2_sigma_m**2)
        )
    )
    s = b * A_v * (sigma - d_sigma)

    az12 = math.atan2(cos_U2 * math.sin(lam), cos_U1 * sin_U2 - sin_U1 * cos_U2 * math.cos(lam))
    az21 = math.atan2(cos_U1 * math.sin(lam), -sin_U1 * cos_U2 + cos_U1 * sin_U2 * math.cos(lam)) + math.pi

    return {
        "distance_m":        s,
        "az12_deg":          (math.degrees(az12) + 360.0) % 360.0,
        "az21_deg":          (math.degrees(az21) + 360.0) % 360.0,
        "convergence_warning": False,
    }


# ---------------------------------------------------------------------------
# Vincenty direct (geodesic destination)
# ---------------------------------------------------------------------------

def vincenty_direct(
    lat1_deg: float,
    lon1_deg: float,
    az12_deg: float,
    dist_m: float,
    ellipsoid: str | None = None,
    tol: float = 1e-12,
    max_iter: int = 1000,
) -> dict:
    """
    Vincenty (1975) direct solution: destination from start + azimuth + distance.

    Parameters
    ----------
    lat1_deg  : start latitude (degrees)
    lon1_deg  : start longitude (degrees)
    az12_deg  : forward azimuth from start (degrees, 0=N clockwise)
    dist_m    : geodesic distance (metres)
    ellipsoid : datum (default WGS84)

    Returns
    -------
    {'lat2_deg': float, 'lon2_deg': float, 'az21_deg': float,
     'convergence_warning': bool}
    """
    ell = _get_ellipsoid(ellipsoid)
    a = ell.a
    f = ell.f
    b = a * (1.0 - f)

    phi1 = math.radians(lat1_deg)
    alpha1 = math.radians(az12_deg)
    s = dist_m

    sin_alpha1 = math.sin(alpha1)
    cos_alpha1 = math.cos(alpha1)

    U1 = math.atan((1.0 - f) * math.tan(phi1))
    sin_U1, cos_U1 = math.sin(U1), math.cos(U1)

    sigma1 = math.atan2(math.tan(U1), cos_alpha1)
    sin_alpha = cos_U1 * sin_alpha1
    cos2_alpha = 1.0 - sin_alpha**2
    u2 = cos2_alpha * (a**2 - b**2) / b**2

    A_v = 1.0 + u2 / 16384.0 * (4096.0 + u2 * (-768.0 + u2 * (320.0 - 175.0 * u2)))
    B_v = u2 / 1024.0 * (256.0 + u2 * (-128.0 + u2 * (74.0 - 47.0 * u2)))

    sigma = s / (b * A_v)
    converged = False
    cos2_sigma_m = sin_sigma = cos_sigma = 0.0

    for _ in range(max_iter):
        cos2_sigma_m = math.cos(2.0 * sigma1 + sigma)
        sin_sigma = math.sin(sigma)
        cos_sigma = math.cos(sigma)
        d_sigma = B_v * sin_sigma * (
            cos2_sigma_m + B_v / 4.0 * (
                cos_sigma * (-1.0 + 2.0 * cos2_sigma_m**2)
                - B_v / 6.0 * cos2_sigma_m * (-3.0 + 4.0 * sin_sigma**2) * (-3.0 + 4.0 * cos2_sigma_m**2)
            )
        )
        sigma_new = s / (b * A_v) + d_sigma
        if abs(sigma_new - sigma) < tol:
            sigma = sigma_new
            converged = True
            break
        sigma = sigma_new

    if not converged:
        warnings.warn(
            "vincenty_direct: failed to converge. Result may be inaccurate.",
            stacklevel=2,
        )

    cos2_sigma_m = math.cos(2.0 * sigma1 + sigma)
    sin_sigma = math.sin(sigma)
    cos_sigma = math.cos(sigma)

    phi2 = math.atan2(
        sin_U1 * cos_sigma + cos_U1 * sin_sigma * cos_alpha1,
        (1.0 - f) * math.sqrt(
            sin_alpha**2
            + (sin_U1 * sin_sigma - cos_U1 * cos_sigma * cos_alpha1) ** 2
        ),
    )
    lam = math.atan2(
        sin_sigma * sin_alpha1,
        cos_U1 * cos_sigma - sin_U1 * sin_sigma * cos_alpha1,
    )
    C = f / 16.0 * cos2_alpha * (4.0 + f * (4.0 - 3.0 * cos2_alpha))
    L = lam - (1.0 - C) * f * sin_alpha * (
        sigma + C * sin_sigma * (
            cos2_sigma_m + C * cos_sigma * (-1.0 + 2.0 * cos2_sigma_m**2)
        )
    )
    alpha2 = math.atan2(sin_alpha, -sin_U1 * sin_sigma + cos_U1 * cos_sigma * cos_alpha1) + math.pi

    return {
        "lat2_deg":          math.degrees(phi2),
        "lon2_deg":          (math.degrees(L) + math.degrees(math.radians(lon1_deg)) + 540.0) % 360.0 - 180.0,
        "az21_deg":          (math.degrees(alpha2)) % 360.0,
        "convergence_warning": not converged,
    }


# ---------------------------------------------------------------------------
# Grid ↔ Ground (combined scale factor)
# ---------------------------------------------------------------------------

def grid_to_ground(
    grid_distance_m: float,
    elevation_m: float,
    k_projection: float,
    earth_radius_m: float = 6_371_000.0,
) -> dict:
    """
    Convert a grid distance to ground distance using the combined scale factor.

    combined_scale_factor (CSF) = k_projection × k_elevation
    k_elevation = R / (R + h)

    ground_distance = grid_distance / CSF

    Parameters
    ----------
    grid_distance_m  : horizontal grid distance (metres)
    elevation_m      : mean elevation above ellipsoid (metres)
    k_projection     : projection scale factor at the line's midpoint
    earth_radius_m   : mean Earth radius (default 6 371 000 m)

    Returns
    -------
    {'ground_distance_m': float, 'csf': float, 'k_elevation': float}
    """
    k_elev = earth_radius_m / (earth_radius_m + elevation_m)
    csf = k_projection * k_elev
    ground = grid_distance_m / csf
    return {"ground_distance_m": ground, "csf": csf, "k_elevation": k_elev}


# ---------------------------------------------------------------------------
# Geoid undulation note (informational)
# ---------------------------------------------------------------------------

GEOID_NOTE = (
    "Geoid undulations are NOT computed in this module. "
    "All heights are ellipsoidal (h). To obtain orthometric height H: H = h - N_geoid, "
    "where N_geoid is the geoid undulation from an external model (e.g. EGM2008, GEOID18)."
)
