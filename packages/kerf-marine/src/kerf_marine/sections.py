"""
kerf_marine.sections — Hull-section integration.

Provides trapezoidal and Simpson's rule integration of hull cross-sections
defined by half-breadth offset tables.

Terminology
-----------
station     : longitudinal position along the hull (x-coordinate, metres)
waterline   : vertical height above keel (z-coordinate, metres)
half_breadth: half the beam at a given (station, waterline) pair (metres)
offsets     : table of (station, waterline, half_breadth) triples

Integration conventions
-----------------------
Area of a section slice     : integrating 2*y dz over waterline range
Volume of displacement      : integrating section_area dx over station range
First moment about keel     : integrating section_area * z_centroid dx
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OffsetRow:
    """One row in a hull offsets table: (station, waterline, half_breadth)."""
    station: float        # m — longitudinal position from aft (or bow)
    waterline: float      # m — height above keel
    half_breadth: float   # m — y at this (station, waterline)


@dataclass
class SectionSlice:
    """Integrated properties of one transverse hull section."""
    station: float        # m — longitudinal position
    area: float           # m² — full cross-section area (both sides)
    centroid_z: float     # m — vertical centroid above keel
    first_moment_z: float # m³ — area * centroid_z (about keel)
    second_moment_z: float  # m⁴ — I_z (for BM calculation)
    waterplane_half_breadth: float  # m — half-breadth at the waterline level


# ---------------------------------------------------------------------------
# Low-level quadrature
# ---------------------------------------------------------------------------

def _trapz(xs: list[float], ys: list[float]) -> float:
    """Trapezoidal integration of y(x) over xs."""
    if len(xs) < 2:
        return 0.0
    total = 0.0
    for i in range(len(xs) - 1):
        total += 0.5 * (ys[i] + ys[i + 1]) * (xs[i + 1] - xs[i])
    return total


def _simpson(xs: list[float], ys: list[float]) -> float:
    """
    Composite Simpson's rule.  If the number of intervals is odd (even number
    of y-values), the last trapezoid is handled with the trapezoidal rule so
    the function always returns a result.
    """
    n = len(xs)
    if n < 2:
        return 0.0
    if n == 2:
        return _trapz(xs, ys)

    total = 0.0
    i = 0
    while i + 2 < n:
        h0 = xs[i + 1] - xs[i]
        h1 = xs[i + 2] - xs[i + 1]
        # Exact Simpson for equal spacing; Newton–Cotes 1/3 for unequal
        h = h0 + h1
        total += (h / 6.0) * (ys[i] + 4.0 * ys[i + 1] + ys[i + 2])
        i += 2

    # Odd number of intervals → clean up last pair with trapezoid
    if i + 1 < n:
        total += 0.5 * (ys[i] + ys[i + 1]) * (xs[i + 1] - xs[i])

    return total


# ---------------------------------------------------------------------------
# Section-level integration
# ---------------------------------------------------------------------------

def integrate_section(
    waterlines: list[float],
    half_breadths: list[float],
    *,
    method: str = "simpson",
) -> SectionSlice:
    """
    Integrate one transverse cross-section defined by half-breadth offsets.

    Parameters
    ----------
    waterlines    : ascending z-values (m above keel), length >= 2
    half_breadths : y_half at each waterline (m), same length
    method        : 'simpson' (default) or 'trapz'

    Returns
    -------
    SectionSlice with area, centroid_z, first_moment_z, second_moment_z,
    and waterplane_half_breadth (half-breadth at the highest waterline).

    The integration uses *full* breadths (2 * half_breadth) so areas are
    correct full-ship values.
    """
    if len(waterlines) != len(half_breadths):
        raise ValueError("waterlines and half_breadths must have equal length")
    if len(waterlines) < 2:
        raise ValueError("At least 2 waterlines required")

    zs = waterlines
    ys = [2.0 * h for h in half_breadths]  # full breadths

    integrate = _simpson if method == "simpson" else _trapz

    # Cross-section area = ∫ b(z) dz
    area = integrate(zs, ys)

    # First moment about keel = ∫ z·b(z) dz
    z_y = [zs[i] * ys[i] for i in range(len(zs))]
    fm_z = integrate(zs, z_y)

    # Second moment of waterplane area (for BM) = ∫ (1/12) b³ dz integrated
    # across the full section depth.  This is the *sectional* contribution
    # to the longitudinal second moment of area; for a single station it
    # represents I_L at that section.
    # For transverse BM we actually need the waterplane I; that is handled
    # in hydrostatics.py by integrating waterplane half-breadths³ over length.
    # Here we return the sectional I_z (useful for section modulus).
    b3_y = [(ys[i] ** 3) / 12.0 for i in range(len(zs))]
    i_z = integrate(zs, b3_y)

    centroid_z = fm_z / area if area > 0.0 else 0.0
    waterplane_half = half_breadths[-1]  # half-breadth at top waterline

    return SectionSlice(
        station=0.0,           # caller sets station
        area=area,
        centroid_z=centroid_z,
        first_moment_z=fm_z,
        second_moment_z=i_z,
        waterplane_half_breadth=waterplane_half,
    )


# ---------------------------------------------------------------------------
# Whole-hull table integration
# ---------------------------------------------------------------------------

@dataclass
class OffsetTable:
    """
    Hull offsets table: rows of (station, waterline, half_breadth).

    The table may have irregular station / waterline spacing.
    All values in metres.
    """
    rows: list[OffsetRow] = field(default_factory=list)

    def add(self, station: float, waterline: float, half_breadth: float) -> None:
        self.rows.append(OffsetRow(station, waterline, half_breadth))

    def stations(self) -> list[float]:
        return sorted({r.station for r in self.rows})

    def waterlines(self) -> list[float]:
        return sorted({r.waterline for r in self.rows})

    def half_breadths_at_station(self, station: float) -> tuple[list[float], list[float]]:
        """Return (waterlines, half_breadths) for a given station."""
        rows = sorted(
            [r for r in self.rows if r.station == station],
            key=lambda r: r.waterline,
        )
        return [r.waterline for r in rows], [r.half_breadth for r in rows]

    def half_breadths_at_waterline(self, waterline: float) -> tuple[list[float], list[float]]:
        """Return (stations, half_breadths) at a given waterline."""
        rows = sorted(
            [r for r in self.rows if r.waterline == waterline],
            key=lambda r: r.station,
        )
        return [r.station for r in rows], [r.half_breadth for r in rows]


def integrate_sections(
    table: OffsetTable,
    *,
    method: str = "simpson",
) -> list[SectionSlice]:
    """
    Integrate each station section in the offset table.

    Returns a list of SectionSlice objects (one per station), sorted by
    ascending station position.
    """
    slices: list[SectionSlice] = []
    for station in table.stations():
        zs, ys = table.half_breadths_at_station(station)
        if len(zs) < 2:
            continue
        sl = integrate_section(zs, ys, method=method)
        sl.station = station
        slices.append(sl)
    return slices


def box_barge_table(
    length: float,
    beam: float,
    draft: float,
    n_stations: int = 11,
    n_waterlines: int = 5,
) -> OffsetTable:
    """
    Build an OffsetTable for a rectangular box barge.

    Useful for analytic verification (DoD oracles).

    Parameters
    ----------
    length     : m — length between perpendiculars
    beam       : m — full beam
    draft      : m — draft (waterline = draft)
    n_stations : number of equally-spaced stations (min 2)
    n_waterlines : number of equally-spaced waterlines from 0 to draft

    The half-breadth is B/2 at every (station, waterline) except the keel
    (waterline=0) where it is also B/2 (flat floor).
    """
    import numpy as np

    table = OffsetTable()
    for x in np.linspace(0.0, length, n_stations):
        for z in np.linspace(0.0, draft, n_waterlines):
            table.add(float(x), float(z), beam / 2.0)
    return table
