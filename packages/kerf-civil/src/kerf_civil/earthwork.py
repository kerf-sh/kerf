"""
Earthwork volume calculations for road/highway design.

Implements the Average End Area method, which is the standard technique in
highway earthwork quantity estimation.

The Average End Area formula for a prismoidal element of length L between
two cross-sections with areas A₁ and A₂ is:

    V = L * (A₁ + A₂) / 2

Summed across all pairs of adjacent stations, this reduces to the trapezoid
rule applied to the area function A(s).

More accurate methods (Prismoidal formula, Simpson's rule on sections) are
provided as optional alternatives.

Sign convention
---------------
- Cut area:   positive → material to be removed (cost of excavation)
- Fill area:  positive → material to be placed   (cost of fill)

All lengths in metres, areas in m², volumes in m³.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------

def average_end_area_volume(
    areas: Sequence[float],
    station_spacing: float,
) -> float:
    """Compute total volume using the Average End Area method.

    Parameters
    ----------
    areas:
        Sequence of cross-sectional areas A₀, A₁, …, Aₙ measured at equally
        spaced stations.
    station_spacing:
        Horizontal distance between consecutive stations (metres).

    Returns
    -------
    float
        Total volume in m³.

    Notes
    -----
    For a uniform prism (all areas equal to A and spacing L between n+1
    sections spanning n intervals):

        V = n * L * A  (exact prismatic volume)

    The average-end-area formula also returns exactly n * L * A for a
    uniform prism, so it coincides with the trapezoid rule.
    """
    if len(areas) < 2:
        return 0.0
    total = 0.0
    for i in range(len(areas) - 1):
        total += (areas[i] + areas[i + 1]) / 2.0 * station_spacing
    return total


def average_end_area_volume_variable(
    areas: Sequence[float],
    stations: Sequence[float],
) -> float:
    """Average End Area with variable station spacing.

    Parameters
    ----------
    areas:
        Cross-sectional areas at each station.
    stations:
        Station values (horizontal chainage, metres).  Must be the same
        length as *areas* and strictly increasing.

    Returns
    -------
    float
        Total volume in m³.
    """
    if len(areas) != len(stations):
        raise ValueError("areas and stations must have the same length")
    if len(areas) < 2:
        return 0.0
    total = 0.0
    for i in range(len(areas) - 1):
        L = stations[i + 1] - stations[i]
        if L < 0:
            raise ValueError(f"stations must be strictly increasing; got {stations[i]} -> {stations[i+1]}")
        total += (areas[i] + areas[i + 1]) / 2.0 * L
    return total


def prismoidal_volume(
    areas: Sequence[float],
    mid_areas: Sequence[float],
    station_spacing: float,
) -> float:
    """Prismoidal formula: V = (L/6) * (A₁ + 4*Aₘ + A₂) for each interval.

    More accurate than average-end-area for curved features.

    Parameters
    ----------
    areas:
        Areas at the ends of each interval (n+1 values for n intervals).
    mid_areas:
        Areas at the midpoint of each interval (n values).
    station_spacing:
        Horizontal distance between end stations (metres).
    """
    if len(mid_areas) != len(areas) - 1:
        raise ValueError("mid_areas must have one fewer entry than areas")
    total = 0.0
    L = station_spacing
    for i in range(len(mid_areas)):
        total += (L / 6.0) * (areas[i] + 4.0 * mid_areas[i] + areas[i + 1])
    return total


# ---------------------------------------------------------------------------
# Mass haul helpers
# ---------------------------------------------------------------------------

@dataclass
class MassHaulOrdinate:
    """A single entry in a mass haul diagram.

    Attributes
    ----------
    station:
        Chainage (metres).
    cut_vol:
        Cumulative cut volume to this station (m³).
    fill_vol:
        Cumulative fill volume to this station (m³).
    mass_ordinate:
        Cumulative corrected mass ordinate = sum(cut) − sum(fill * swell_factor).
        Positive = net excess (potential waste); negative = net deficit (borrow).
    """

    station: float
    cut_vol: float
    fill_vol: float
    mass_ordinate: float


def mass_haul(
    stations: Sequence[float],
    cut_areas: Sequence[float],
    fill_areas: Sequence[float],
    swell_factor: float = 1.25,
) -> list[MassHaulOrdinate]:
    """Compute the mass haul (Brückner) curve.

    Parameters
    ----------
    stations:
        Station chainage values (strictly increasing, metres).
    cut_areas:
        Cross-sectional cut area at each station (m²).
    fill_areas:
        Cross-sectional fill area at each station (m²).
    swell_factor:
        Volume expansion factor for cut material (dimensionless).
        Typical: 1.25 for common earth.

    Returns
    -------
    list[MassHaulOrdinate]
        Ordered list of mass haul ordinates.
    """
    if not (len(stations) == len(cut_areas) == len(fill_areas)):
        raise ValueError("stations, cut_areas, fill_areas must have the same length")

    ordinates: list[MassHaulOrdinate] = []
    cumulative_cut = 0.0
    cumulative_fill = 0.0
    mass = 0.0

    ordinates.append(
        MassHaulOrdinate(
            station=stations[0],
            cut_vol=0.0,
            fill_vol=0.0,
            mass_ordinate=0.0,
        )
    )

    for i in range(1, len(stations)):
        L = stations[i] - stations[i - 1]
        dV_cut = (cut_areas[i - 1] + cut_areas[i]) / 2.0 * L
        dV_fill = (fill_areas[i - 1] + fill_areas[i]) / 2.0 * L
        cumulative_cut += dV_cut
        cumulative_fill += dV_fill
        mass += dV_cut - dV_fill * swell_factor
        ordinates.append(
            MassHaulOrdinate(
                station=stations[i],
                cut_vol=cumulative_cut,
                fill_vol=cumulative_fill,
                mass_ordinate=mass,
            )
        )

    return ordinates
