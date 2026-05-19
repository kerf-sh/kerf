"""
Raymer conceptual aircraft sizing — weight-fraction method.

Exported symbols
----------------
- :class:`MissionProfile`     — ordered list of mission segments
- :class:`MissionSegment`     — one segment with W_end/W_start fraction
- :class:`SegmentKind`        — enumeration of segment types
- :class:`AircraftParams`     — design requirements / regression coefficients
- :func:`size_aircraft`       — main sizing entry-point
- :func:`breguet_range_fraction` — standalone Breguet W_end/W_start
- :func:`breguet_range_nm`    — inverse Breguet, range from weights
- ``RAYMER_EMPTY_WEIGHT_COEFFICIENTS`` — Raymer Table 6.2 A, C values
"""

from .mission_profile import MissionProfile, MissionSegment, SegmentKind
from .raymer import (
    RAYMER_EMPTY_WEIGHT_COEFFICIENTS,
    AircraftParams,
    SizingResult,
    breguet_range_fraction,
    breguet_range_nm,
    size_aircraft,
)

__all__ = [
    "MissionProfile",
    "MissionSegment",
    "SegmentKind",
    "AircraftParams",
    "SizingResult",
    "size_aircraft",
    "breguet_range_fraction",
    "breguet_range_nm",
    "RAYMER_EMPTY_WEIGHT_COEFFICIENTS",
]
