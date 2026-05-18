"""
Corridor model — sweep a typical cross-section along a horizontal alignment
to produce a series of cross-sections and a 3-D corridor surface.

This module is deliberately pure-Python (no NumPy dependency) so it can be
imported in any environment.  For numerical work, callers can convert the
returned point lists to numpy arrays.

Terminology (AASHTO)
--------------------
  BL / BR  — edge of travel lane (left/right)
  SL / SR  — shoulder edge (left/right)
  DTW      — ditch toe of the slope (top of embankment or bottom of cut)

A TypicalSection defines widths and slopes; the Corridor sweeps it at
requested stations to produce a CrossSection list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Typical section definition
# ---------------------------------------------------------------------------

@dataclass
class TypicalSection:
    """Simple symmetric two-lane typical section.

    Parameters
    ----------
    lane_width:
        Width of a single travel lane (metres).
    shoulder_width:
        Width of the shoulder (metres).
    cut_slope:
        Cut backslope ratio (H:V).  E.g. 2.0 means 2 horizontal : 1 vertical.
    fill_slope:
        Fill foreslope ratio (H:V).
    lanes_each_side:
        Number of lanes each side of the centreline.
    crown_slope_pct:
        Normal crown (cross-fall) slope, percent.  Positive = falls away
        from centreline.
    """

    lane_width: float = 3.65
    shoulder_width: float = 2.4
    cut_slope: float = 2.0
    fill_slope: float = 2.0
    lanes_each_side: int = 1
    crown_slope_pct: float = 2.0

    def pavement_half_width(self) -> float:
        """Horizontal distance from centreline to edge of pavement."""
        return self.lane_width * self.lanes_each_side

    def total_half_width_flat(self) -> float:
        """Horizontal distance from centreline to shoulder break (no daylight slope)."""
        return self.pavement_half_width() + self.shoulder_width


# ---------------------------------------------------------------------------
# Cross-section point (station, offset, elevation)
# ---------------------------------------------------------------------------

@dataclass
class CrossSectionPoint:
    """A single point on a cross-section.

    Attributes
    ----------
    offset:
        Lateral offset from centreline (metres).  Positive = right.
    elevation:
        Ground-referenced elevation (metres).
    label:
        Optional label (e.g. "CL", "edge_lane", "shoulder", "daylight").
    """

    offset: float
    elevation: float
    label: str = ""


@dataclass
class CrossSection:
    """One cross-section perpendicular to the alignment at a given station.

    Attributes
    ----------
    station:
        Chainage along the alignment (metres).
    cl_elevation:
        Centreline design elevation (metres).
    points:
        Ordered list of cross-section points, left to right.
    """

    station: float
    cl_elevation: float
    points: list[CrossSectionPoint] = field(default_factory=list)

    def half_section(self, side: str) -> list[CrossSectionPoint]:
        """Return points for one side ('left' or 'right')."""
        if side == "left":
            return [p for p in self.points if p.offset <= 0]
        return [p for p in self.points if p.offset >= 0]

    def cut_area(self) -> float:
        """Approximate cut area (m²) using the shoelace formula on the subgrade polygon.

        Returns the cross-sectional area of material to be removed (positive for cut).
        Only valid when a ground surface is available — for the simplified
        corridor model (no DTM) this returns 0.0.
        """
        return 0.0

    def fill_area(self) -> float:
        """Approximate fill area (m²) — see cut_area notes."""
        return 0.0


# ---------------------------------------------------------------------------
# Corridor
# ---------------------------------------------------------------------------

@dataclass
class Corridor:
    """3-D corridor — a typical section swept along a horizontal alignment.

    The corridor computes design cross-sections at requested stations.  It
    does **not** require a ground DTM; daylight points are computed using
    the design subgrade only (flat natural ground at the centreline elevation
    is assumed when no DTM is supplied).

    Parameters
    ----------
    h_alignment:
        A ``HorizontalAlignment`` (or any object with a ``total_length()`` method).
    v_alignment:
        A ``VerticalAlignment`` with an ``elev_at_station(s)`` method.
    typical_section:
        The standard cross-section template.
    """

    h_alignment: object  # HorizontalAlignment (avoid circular import)
    v_alignment: object  # VerticalAlignment
    typical_section: TypicalSection = field(default_factory=TypicalSection)

    def cross_section_at(self, station: float) -> CrossSection:
        """Compute the design cross-section at *station*.

        The cross-section is constructed using the typical section geometry
        and the design profile elevation at the centreline.

        Superelevation rotation is not applied in this baseline implementation
        (normal crown only).
        """
        cl_elev = self.v_alignment.elev_at_station(station)
        ts = self.typical_section
        crown = ts.crown_slope_pct / 100.0

        points: list[CrossSectionPoint] = []

        for sign, side in [(-1, "left"), (1, "right")]:
            pw = ts.pavement_half_width()
            sw = ts.shoulder_width
            # Edge of lane
            e_lane = sign * pw
            e_lane_elev = cl_elev - crown * pw  # falls away from CL
            # Edge of shoulder
            e_shoulder = sign * (pw + sw)
            e_shoulder_elev = e_lane_elev - crown * sw

            # Daylight point — simplified: assume flat ground at shoulder break elev
            # Slope: cut or fill decided by sign of subgrade cut-depth (always cut here)
            slope = ts.cut_slope
            # For a flat natural ground model: daylight offset = shoulder break
            e_daylight = e_shoulder
            e_daylight_elev = e_shoulder_elev

            if side == "left":
                points.insert(0, CrossSectionPoint(e_daylight, e_daylight_elev, f"daylight_{side}"))
                points.insert(1, CrossSectionPoint(e_shoulder, e_shoulder_elev, f"shoulder_{side}"))
                points.insert(2, CrossSectionPoint(e_lane, e_lane_elev, f"edge_lane_{side}"))
            else:
                points.append(CrossSectionPoint(e_lane, e_lane_elev, f"edge_lane_{side}"))
                points.append(CrossSectionPoint(e_shoulder, e_shoulder_elev, f"shoulder_{side}"))
                points.append(CrossSectionPoint(e_daylight, e_daylight_elev, f"daylight_{side}"))

        # Centreline point inserted in the middle
        cl_idx = len(points) // 2
        points.insert(cl_idx, CrossSectionPoint(0.0, cl_elev, "CL"))

        return CrossSection(station=station, cl_elevation=cl_elev, points=points)

    def cross_sections(self, interval: float = 20.0) -> list[CrossSection]:
        """Return a list of cross-sections at a fixed *interval* (metres)."""
        L = self.h_alignment.total_length()
        sections: list[CrossSection] = []
        s = 0.0
        while s <= L + 1e-9:
            sections.append(self.cross_section_at(min(s, L)))
            s += interval
        if abs(sections[-1].station - L) > 1e-6:
            sections.append(self.cross_section_at(L))
        return sections

    def surface_points(self, interval: float = 20.0) -> list[tuple[float, float, float]]:
        """Return (station, offset, elevation) triples for all cross-section points.

        Useful for downstream 3-D mesh generation or visualisation.
        """
        result: list[tuple[float, float, float]] = []
        for xs in self.cross_sections(interval):
            for pt in xs.points:
                result.append((xs.station, pt.offset, pt.elevation))
        return result
