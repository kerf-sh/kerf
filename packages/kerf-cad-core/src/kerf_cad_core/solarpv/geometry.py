"""
kerf_cad_core.solarpv.geometry — canonical Spencer (1971) solar-geometry formulas.

This module is the single source of truth for the shared solar-geometry
primitives used by both kerf_cad_core.solarpv (PV sizing) and kerf_energy
(building-energy / clear-sky irradiance).  Neither package should re-implement
these formulas; import from here instead.

Public API
----------
solar_declination_deg(day_of_year)
    Spencer (1971) Fourier declination δ (degrees).

equation_of_time_spencer_min(day_of_year)
    Full Spencer (1971) equation-of-time E (minutes) — Fourier series.

equation_of_time_approx_min(day_of_year)
    Simplified equation-of-time approximation (minutes) — simpler
    trigonometric form, ≈ ±1 min vs Spencer full series.

solar_hour_angle_deg(solar_time_h)
    Hour angle ω (degrees) from solar time (hours, 0–24).

References
----------
Spencer, J.W. (1971). Fourier series representation of the position of the
  sun.  *Search*, 2(5), 172.
Duffie, J.A. & Beckman, W.A. (2013). *Solar Engineering of Thermal
  Processes*, 4th ed.

Author: imranparuk
"""
from __future__ import annotations

import math


def solar_declination_deg(day_of_year: int) -> float:
    """Return solar declination δ (degrees) for day-of-year *day_of_year*.

    Uses the Spencer (1971) Fourier approximation.  Accuracy ≈ ±0.01°.

    Parameters
    ----------
    day_of_year : int
        Julian day number (1 = 1 Jan, 365 = 31 Dec).

    Returns
    -------
    float
        Declination in degrees.  Range ≈ −23.45° to +23.45°.
    """
    B = 2.0 * math.pi * (day_of_year - 1) / 365.0
    delta_rad = (
        0.006918
        - 0.399912 * math.cos(B)
        + 0.070257 * math.sin(B)
        - 0.006758 * math.cos(2 * B)
        + 0.000907 * math.sin(2 * B)
        - 0.002697 * math.cos(3 * B)
        + 0.00148  * math.sin(3 * B)
    )
    return math.degrees(delta_rad)


def equation_of_time_spencer_min(day_of_year: int) -> float:
    """Return the equation of time E (minutes) via full Spencer (1971) Fourier series.

    This is the more accurate of the two EoT approximations in this module
    (error < 0.5 min vs astronomical truth).  Preferred for load calculations
    that require precise solar-noon timing.

    Parameters
    ----------
    day_of_year : int
        Julian day number (1–365).

    Returns
    -------
    float
        E in minutes (positive → solar noon before clock noon).
    """
    B = 2.0 * math.pi * (day_of_year - 1) / 365.0
    eot_rad = (
        0.000075
        + 0.001868 * math.cos(B)
        - 0.032077 * math.sin(B)
        - 0.014615 * math.cos(2 * B)
        - 0.04089  * math.sin(2 * B)
    )
    return eot_rad * 229.18  # radians → minutes


def equation_of_time_approx_min(day_of_year: int) -> float:
    """Return the equation of time E (minutes) via the simpler trigonometric form.

    This approximation (≈ ±1 min vs astronomical truth) is adequate for PV
    yield and shading calculations where sub-minute accuracy is not required.

    Parameters
    ----------
    day_of_year : int
        Julian day number (1–365).

    Returns
    -------
    float
        E in minutes (positive → solar noon before clock noon).
    """
    B = 2.0 * math.pi * (day_of_year - 1) / 365.0
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def solar_hour_angle_deg(solar_time_h: float) -> float:
    """Return the hour angle ω (degrees) from solar time.

    ω = 0 at solar noon, positive in the afternoon, negative in the morning.

    Parameters
    ----------
    solar_time_h : float
        Solar (apparent) time in decimal hours (0–24).

    Returns
    -------
    float
        Hour angle in degrees (range approximately −180° to +180°).
    """
    return 15.0 * (solar_time_h - 12.0)
