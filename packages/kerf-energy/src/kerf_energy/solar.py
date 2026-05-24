"""
Solar geometry and clear-sky irradiance.

The Spencer (1971) declination, equation-of-time, and hour-angle primitives
are imported from the canonical home:
  kerf_cad_core.solarpv.geometry

This avoids duplicating the Fourier coefficients across packages.

References:
  ASHRAE Fundamentals 2021, Ch. 14 — Climatic Design Information.
  ASHRAE Fundamentals 2021, Ch. 15 — Fenestration.
  Spencer, J. N. (1971). Fourier series representation of the position of
    the sun.  Search, 2(5), 172.
  Iqbal, M. (1983). An Introduction to Solar Radiation. Academic Press.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from kerf_cad_core.solarpv.geometry import (
    solar_declination_deg,
    equation_of_time_spencer_min as equation_of_time_minutes,
    solar_hour_angle_deg as hour_angle_deg,
)

# Re-export so existing callers of `from kerf_energy.solar import ...` keep working.
__all__ = [
    "day_of_year",
    "solar_declination_deg",
    "equation_of_time_minutes",
    "hour_angle_deg",
    "local_to_solar_time",
    "solar_position",
    "solar_noon_altitude_deg",
    "direct_normal_irradiance_ashrae",
    "diffuse_horizontal_irradiance_ashrae",
    "ClearSkyIrradiance",
    "clear_sky_irradiance",
]


# ---------------------------------------------------------------------------
# Day-of-year helpers
# ---------------------------------------------------------------------------

def day_of_year(d: date) -> int:
    """Return the day-of-year (1–366) for *d*."""
    return d.timetuple().tm_yday


def local_to_solar_time(
    local_time_hours: float,
    longitude_deg: float,
    standard_meridian_deg: float,
    doy: int,
) -> float:
    """Convert local standard time to apparent solar time.

    Parameters
    ----------
    local_time_hours:
        Local standard time in decimal hours.
    longitude_deg:
        Site longitude (degrees, east positive).
    standard_meridian_deg:
        Standard meridian of the local time zone (degrees, east positive).
    doy:
        Day of year.

    Returns
    -------
    float
        Apparent solar time in decimal hours.
    """
    eot = equation_of_time_minutes(doy)
    # Longitude correction: 4 minutes per degree
    longitude_correction = 4.0 * (longitude_deg - standard_meridian_deg)
    solar_time = local_time_hours + (eot + longitude_correction) / 60.0
    return solar_time


# ---------------------------------------------------------------------------
# Solar altitude and azimuth
# ---------------------------------------------------------------------------

def solar_position(
    latitude_deg: float,
    declination_deg: float,
    hour_angle_deg_: float,
) -> tuple[float, float]:
    """Return (altitude_deg, azimuth_deg) for the given solar geometry.

    Parameters
    ----------
    latitude_deg:
        Site latitude in degrees (north positive).
    declination_deg:
        Solar declination in degrees.
    hour_angle_deg_:
        Solar hour angle in degrees (0 at noon, negative AM).

    Returns
    -------
    (altitude_deg, azimuth_deg)
        Solar altitude angle above horizontal (degrees, 0–90).
        Solar azimuth measured clockwise from north (degrees, 0–360).
    """
    lat = math.radians(latitude_deg)
    dec = math.radians(declination_deg)
    ha = math.radians(hour_angle_deg_)

    # Altitude
    sin_alt = (
        math.sin(lat) * math.sin(dec)
        + math.cos(lat) * math.cos(dec) * math.cos(ha)
    )
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude_rad = math.asin(sin_alt)
    altitude_deg = math.degrees(altitude_rad)

    # Azimuth (from south, west positive) — then convert to N-clockwise
    cos_alt = math.cos(altitude_rad)
    if abs(cos_alt) < 1e-9:
        # Sun is at zenith
        azimuth_deg = 0.0
    else:
        cos_az = (math.sin(dec) - math.sin(lat) * sin_alt) / (
            math.cos(lat) * cos_alt
        )
        cos_az = max(-1.0, min(1.0, cos_az))
        azimuth_from_south = math.degrees(math.acos(cos_az))
        # Determine east/west
        if hour_angle_deg_ > 0:
            # Afternoon → sun is west of south
            azimuth_from_south_signed = azimuth_from_south
        else:
            azimuth_from_south_signed = -azimuth_from_south
        # Convert from south-based to north-clockwise
        azimuth_deg = (azimuth_from_south_signed + 180.0) % 360.0

    return altitude_deg, azimuth_deg


def solar_noon_altitude_deg(latitude_deg: float, doy: int) -> float:
    """Return the solar altitude at solar noon for the given latitude and day.

    Parameters
    ----------
    latitude_deg:
        Site latitude (degrees, north positive).
    doy:
        Day of year.

    Returns
    -------
    float
        Solar altitude at solar noon (degrees).
        At equinox (doy ≈ 80 or 264) on the equator this is 90°.
    """
    dec = solar_declination_deg(doy)
    # At solar noon, hour angle = 0
    alt, _ = solar_position(latitude_deg, dec, 0.0)
    return alt


# ---------------------------------------------------------------------------
# ASHRAE clear-sky direct-normal irradiance (DNI)
# ---------------------------------------------------------------------------

# ASHRAE 2021 Fundamentals Table 1, Ch. 15 — A, B, C constants for 21st day
# of each month.
_ASHRAE_CLEAR_SKY: dict[int, tuple[float, float, float]] = {
    # month: (A W/m², B dimensionless, C dimensionless)
    1:  (1202, 0.141, 0.103),
    2:  (1187, 0.142, 0.104),
    3:  (1164, 0.149, 0.109),
    4:  (1130, 0.164, 0.120),
    5:  (1106, 0.177, 0.130),
    6:  (1092, 0.185, 0.137),
    7:  (1093, 0.186, 0.138),
    8:  (1107, 0.182, 0.134),
    9:  (1136, 0.165, 0.121),
    10: (1166, 0.152, 0.111),
    11: (1190, 0.144, 0.106),
    12: (1204, 0.141, 0.103),
}


def _month_from_doy(doy: int) -> int:
    """Return the month (1–12) for the given day-of-year."""
    days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
    for m in range(1, 13):
        if days[m - 1] < doy <= days[m]:
            return m
    return 12


def direct_normal_irradiance_ashrae(
    solar_altitude_deg: float,
    doy: int,
) -> float:
    """ASHRAE clear-sky direct-normal irradiance (W/m²).

    Parameters
    ----------
    solar_altitude_deg:
        Solar altitude angle above horizontal (degrees).
    doy:
        Day of year (used to select seasonal ASHRAE coefficients).

    Returns
    -------
    float
        Direct-normal irradiance in W/m².  Returns 0 if sun is below horizon.
    """
    if solar_altitude_deg <= 0:
        return 0.0

    month = _month_from_doy(doy)
    A, B, _ = _ASHRAE_CLEAR_SKY[month]

    # DNI = A / exp(B / sin(altitude))
    sin_alt = math.sin(math.radians(solar_altitude_deg))
    if sin_alt <= 0:
        return 0.0
    dni = A / math.exp(B / sin_alt)
    return max(0.0, dni)


def diffuse_horizontal_irradiance_ashrae(
    direct_normal_irradiance: float,
    solar_altitude_deg: float,
    doy: int,
) -> float:
    """ASHRAE clear-sky diffuse horizontal irradiance (W/m²).

    Parameters
    ----------
    direct_normal_irradiance:
        Direct normal irradiance (W/m²).
    solar_altitude_deg:
        Solar altitude angle (degrees).
    doy:
        Day of year.

    Returns
    -------
    float
        Diffuse horizontal irradiance (W/m²).
    """
    if solar_altitude_deg <= 0:
        return 0.0

    month = _month_from_doy(doy)
    A, B, C = _ASHRAE_CLEAR_SKY[month]

    # DHI = C × DNI
    return C * direct_normal_irradiance


@dataclass
class ClearSkyIrradiance:
    """Bundle of ASHRAE clear-sky irradiance components."""

    direct_normal_w_m2: float
    diffuse_horizontal_w_m2: float
    global_horizontal_w_m2: float
    solar_altitude_deg: float


def clear_sky_irradiance(
    latitude_deg: float,
    longitude_deg: float,
    doy: int,
    solar_time_hours: float,
) -> ClearSkyIrradiance:
    """Compute ASHRAE clear-sky irradiance components.

    Parameters
    ----------
    latitude_deg:
        Site latitude (degrees, north positive).
    longitude_deg:
        Site longitude (degrees, east positive).  Not used for solar
        position (solar time assumed given), kept for future use.
    doy:
        Day of year.
    solar_time_hours:
        Apparent solar time (decimal hours).

    Returns
    -------
    ClearSkyIrradiance
        DNI, DHI, GHI, and solar altitude.
    """
    dec = solar_declination_deg(doy)
    ha = hour_angle_deg(solar_time_hours)
    alt_deg, _ = solar_position(latitude_deg, dec, ha)

    dni = direct_normal_irradiance_ashrae(alt_deg, doy)
    dhi = diffuse_horizontal_irradiance_ashrae(dni, alt_deg, doy)

    # Global horizontal: GHI = DNI·sin(alt) + DHI
    sin_alt = max(0.0, math.sin(math.radians(alt_deg)))
    ghi = dni * sin_alt + dhi

    return ClearSkyIrradiance(
        direct_normal_w_m2=dni,
        diffuse_horizontal_w_m2=dhi,
        global_horizontal_w_m2=ghi,
        solar_altitude_deg=alt_deg,
    )
